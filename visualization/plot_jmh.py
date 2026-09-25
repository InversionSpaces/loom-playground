#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Compare vtPerTask and vtPerWorker JMH results by parallelism and tasksPerSlot."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_PARAMS = {"parallelism", "tasksPerSlot"}
COLORS = {"VT-PER-TASK": "#0072B2", "VT-PER-WORKER": "#D55E00"}
BENCHMARK_METHODS = {"vtPerTask": "VT-PER-TASK", "vtPerWorker": "VT-PER-WORKER"}
NANOSECONDS = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000,
               "min": 60_000_000_000, "hr": 3_600_000_000_000}


def per_task_cost(metric, mode, total_tasks):
    """Normalize a batch score and its error interval to elapsed ns/task."""
    score = float(metric["score"])
    if not math.isfinite(score) or score <= 0:
        raise ValueError("Per-task plots require finite, positive JMH scores")
    try:
        error = float(metric.get("scoreError", "NaN"))
    except (ValueError, TypeError):
        error = math.nan
    numerator, denominator = metric["scoreUnit"].split("/")
    if mode == "thrpt" and numerator == "ops" and denominator in NANOSECONDS:
        factor = NANOSECONDS[denominator] / total_tasks
        cost = factor / score
        # Inverting throughput reverses the bounds and makes errors asymmetric.
        bounds = ((factor / (score + error), factor / (score - error))
                  if math.isfinite(error) and 0 <= error < score else None)
    elif mode in {"avgt", "ss"} and denominator == "op" and numerator in NANOSECONDS:
        factor = NANOSECONDS[numerator] / total_tasks
        cost = score * factor
        bounds = (((score - error) * factor, (score + error) * factor)
                  if math.isfinite(error) and 0 <= error < score else None)
    else:
        raise ValueError(f"Unsupported per-task normalization: {mode}, {metric['scoreUnit']}")
    errors = (cost - bounds[0], bounds[1] - cost) if bounds else None
    return cost, errors


def load_groups(report):
    records = json.loads(report.read_text())
    if not isinstance(records, list):
        raise ValueError("Expected a JMH JSON array of benchmark results")
    groups = defaultdict(list)
    seen = set()
    skipped = 0
    for record in records:
        params = record.get("params", {})
        benchmark, _, method = record["benchmark"].rpartition(".")
        if method not in BENCHMARK_METHODS or not REQUIRED_PARAMS.issubset(params):
            skipped += 1
            continue
        parallelism = int(params["parallelism"])
        tasks = int(params["tasksPerSlot"])
        if parallelism <= 0 or tasks <= 0:
            raise ValueError("parallelism and tasksPerSlot must be positive")
        metric = record["primaryMetric"]
        score, error = per_task_cost(metric, record["mode"], parallelism * tasks)
        # Keep other workloads, JMH worker counts, modes and units separate.
        extra = tuple(sorted((k, str(v)) for k, v in params.items()
                             if k not in REQUIRED_PARAMS))
        key = (benchmark, record["mode"], metric["scoreUnit"],
               record.get("threads", 1), extra, parallelism)
        executor = BENCHMARK_METHODS[method]
        point_key = (key, executor, tasks)
        if point_key in seen:
            raise ValueError(f"Duplicate result for {record['benchmark']}: {params}")
        seen.add(point_key)
        groups[key].append((executor, tasks, score, error))
    if not groups:
        raise ValueError("No vtPerTask/vtPerWorker results with parallelism and tasksPerSlot")
    if skipped:
        print(f"Skipped {skipped} result(s) with unrelated methods or missing parameters.", file=sys.stderr)
    return groups


def cost_ratios(points):
    """Pair identical task counts and divide fresh-thread cost by worker cost."""
    per_task = {p[1]: p[2] for p in points if p[0] == "VT-PER-TASK"}
    per_worker = {p[1]: p[2] for p in points if p[0] == "VT-PER-WORKER"}
    if not per_task or per_task.keys() != per_worker.keys():
        raise ValueError("Ratio charts require both executor types at every tasksPerSlot value")
    return [(tasks, per_task[tasks] / per_worker[tasks]) for tasks in sorted(per_task)]


def plot_groups(groups, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator

    output.mkdir(parents=True, exist_ok=True)
    executors = sorted({point[0] for points in groups.values() for point in points})
    colors = dict(COLORS)
    palette = ["#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]
    for i, executor in enumerate(e for e in executors if e not in colors):
        colors[executor] = palette[i % len(palette)]

    # Share positive limits and ten geometrically spaced ticks across all charts.
    ymin = 1
    ymax = max(p[2] + (p[3][1] if p[3] is not None else 0)
               for points in groups.values() for p in points)
    ymax = max(ymax * 1.05, ymin * 10)
    ticks = [ymin * (ymax / ymin) ** (i / 9) for i in range(10)]
    ticks[0], ticks[-1] = ymin, ymax

    def draw_chart(ax, key, points, linestyle="-", marker="o"):
        benchmark, mode, unit, jmh_threads, extra, parallelism = key
        endpoints = []
        for executor in executors:
            series = sorted((p for p in points if p[0] == executor), key=lambda p: p[1])
            if not series:
                continue
            ax.plot([p[1] for p in series], [p[2] for p in series],
                    marker=marker, linestyle=linestyle, linewidth=2,
                    color=colors[executor], label=executor)
            endpoints.append((series[-1][1], series[-1][2], colors[executor]))
            errors = [p for p in series if p[3] is not None]
            if errors:
                ax.errorbar([p[1] for p in errors], [p[2] for p in errors],
                            yerr=[[p[3][0] for p in errors], [p[3][1] for p in errors]],
                            fmt="none", capsize=4,
                            color=colors[executor], alpha=0.65)

        xs = sorted({p[1] for p in points})
        ax.set_yscale("log")
        ax.set_xscale("log")
        ax.set_xticks(xs, labels=[str(x) for x in xs])
        ax.minorticks_off()

        ax.set_ylim(ymin, ymax)
        ax.yaxis.set_major_locator(FixedLocator(ticks))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.4g}"))
        ax.set_xlabel("Tasks per concurrency slot (log scale)")
        ax.set_ylabel("Elapsed time per task (ns/task, log scale; lower is better)")
        detail = ", ".join(f"{k}={v}" for k, v in extra)
        title = f"{benchmark}\nParallelism={parallelism}"
        if detail:
            title += f" · {detail}"
        title += f" · JMH threads={jmh_threads}"
        ax.set_title(title, fontsize=11, pad=14)
        ax.grid(True, alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(title="Executor type")
        return endpoints

    footer = "Batch cost ÷ tasks per batch, including executor overhead. Error bars: transformed JMH interval."
    ordered_groups = sorted(groups.items())
    for key, points in ordered_groups:
        benchmark, mode, unit, jmh_threads, extra, parallelism = key
        fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
        draw_chart(ax, key, points)
        fig.supxlabel(footer, fontsize=9, color="#555555")
        # A short hash avoids collisions after sanitizing arbitrary parameter values.
        variant = hashlib.sha256(repr(key[:-1]).encode()).hexdigest()[:8]
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", benchmark)
        stem = f"{name}-parallelism-{parallelism}-{variant}"
        for extension in ("png", "svg"):
            path = output / f"{stem}.{extension}"
            fig.savefig(path, dpi=180)
            print(path)
        plt.close(fig)

    workloads = defaultdict(list)
    for key, points in ordered_groups:
        workloads[key[:-1]].append((key, points))
    markers = ["o", "s", "^", "D", "v", "P", "X"]
    ratio_colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]
    for workload, entries in workloads.items():
        fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
        ratios = []
        for i, (key, points) in enumerate(entries):
            series = cost_ratios(points)
            ratios.extend(ratio for _, ratio in series)
            ax.plot([tasks for tasks, _ in series], [ratio for _, ratio in series],
                    color=ratio_colors[i % len(ratio_colors)], marker=markers[i % len(markers)],
                    linewidth=2, markersize=7, label=str(key[-1]))

        xs = sorted({p[1] for _, points in entries for p in points})
        ax.set_xscale("log")
        ax.set_xticks(xs, labels=[str(x) for x in xs])
        ax.minorticks_off()
        ax.set_ylim(0, max(1, max(ratios)) * 1.15)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}×"))
        ax.axhline(1, color="#555555", linestyle="--", linewidth=1.3)
        ax.annotate("1× = equal cost", xy=(0.02, 1), xycoords=("axes fraction", "data"),
                    xytext=(0, 6), textcoords="offset points", color="#555555", fontsize=10)
        ax.set_xlabel("Tasks per concurrency slot (log scale)")
        ax.set_ylabel("Cost ratio: VT-PER-TASK / VT-PER-WORKER")
        ax.grid(True, alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        benchmark, mode, unit, jmh_threads, extra = workload
        detail = " · ".join(f"{k}={v}" for k, v in extra)
        ax.set_title(f"Fresh virtual threads vs reused workers\n{benchmark} · {detail + ' · ' if detail else ''}JMH threads={jmh_threads}",
                     fontsize=12, pad=14)
        ax.legend(title="Parallelism", loc="upper left", ncols=min(4, len(entries)))
        fig.supxlabel("Below 1×: fresh threads cost less · Above 1×: reused workers cost less\n"
                      "Ratios of point estimates; confidence intervals are not shown.",
                      fontsize=10, color="#555555")
        suffix = "" if len(workloads) == 1 else "-" + hashlib.sha256(repr(workload).encode()).hexdigest()[:8]
        for extension in ("png", "svg"):
            path = output / f"combined{suffix}.{extension}"
            fig.savefig(path, dpi=180)
            print(path)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?",
                        default=ROOT / "build/reports/jmh/results.json",
                        help="JMH JSON report (default: build/reports/jmh/results.json)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=ROOT / "visualization/plots/tasks",
                        help="Output directory (default: visualization/plots/tasks)")
    args = parser.parse_args()
    try:
        groups = load_groups(args.report)
        plot_groups(groups, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
