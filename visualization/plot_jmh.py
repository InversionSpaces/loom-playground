#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Plot task throughput in one image: rows by tasksPerSlot, columns by method."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_PARAMS = {"parallelism", "tasksPerSlot"}
COLORS = {"QUEUE": "#0072B2", "JOX": "#D55E00", "JOX_TRY": "#009E73"}
BENCHMARK_METHODS = ("vtPerTask", "vtPerWorker")
THROUGHPUT_UNIT = 100_000
SECONDS = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1,
           "min": 60, "hr": 3600}


def task_throughput(metric, mode, total_tasks):
    """Convert a batch score and its confidence interval to tasks/second."""
    score = float(metric["score"])
    if not math.isfinite(score) or score <= 0:
        raise ValueError("Throughput plots require finite, positive JMH scores")
    try:
        error = float(metric.get("scoreError", "NaN"))
    except (ValueError, TypeError):
        error = math.nan
    numerator, denominator = metric["scoreUnit"].split("/")
    valid_error = math.isfinite(error) and 0 <= error < score
    if mode == "thrpt" and numerator == "ops" and denominator in SECONDS:
        factor = total_tasks / SECONDS[denominator]
        throughput = score * factor
        errors = (error * factor, error * factor) if valid_error else None
    elif mode in {"avgt", "ss"} and denominator == "op" and numerator in SECONDS:
        factor = total_tasks / SECONDS[numerator]
        throughput = factor / score
        # Inverting elapsed time reverses the bounds and makes errors asymmetric.
        errors = ((throughput - factor / (score + error),
                   factor / (score - error) - throughput) if valid_error else None)
    else:
        raise ValueError(f"Unsupported throughput normalization: {mode}, {metric['scoreUnit']}")
    return throughput, errors


def report_paths(inputs):
    """Expand report directories in filename order, reading each file once."""
    if isinstance(inputs, Path):
        inputs = [inputs]
    paths = []
    seen = set()
    for source in inputs:
        candidates = sorted(source.glob("*.json")) if source.is_dir() else [source]
        for path in candidates:
            resolved = path.resolve()
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)
    if not paths:
        raise ValueError("No JSON reports found")
    return paths


def load_groups(reports):
    groups = defaultdict(lambda: defaultdict(list))
    seen = {}
    merged_files = 0
    for report in report_paths(reports):
        content = report.read_text()
        if not content.strip():
            print(f"Skipped {report}: empty file", file=sys.stderr)
            continue
        try:
            records = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in {report}: {error}") from error
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise ValueError(f"Expected a JMH JSON array of benchmark results in {report}")
        added = duplicates = skipped = 0
        parallelisms = set()
        for record in records:
            params = record.get("params", {})
            benchmark, _, record_method = record["benchmark"].rpartition(".")
            if record_method not in BENCHMARK_METHODS or not REQUIRED_PARAMS.issubset(params):
                skipped += 1
                continue
            parallelism = int(params["parallelism"])
            tasks = int(params["tasksPerSlot"])
            if parallelism <= 0 or tasks <= 0:
                raise ValueError(f"parallelism and tasksPerSlot must be positive in {report}")
            handoff = str(params.get("handoff", "QUEUE"))
            metric = record["primaryMetric"]
            throughput, error = task_throughput(metric, record["mode"], parallelism * tasks)
            # Keep distinct workloads, modes and JMH thread counts in separate rows.
            extra = tuple(sorted((k, str(v)) for k, v in params.items()
                                 if k not in REQUIRED_PARAMS | {"handoff"}))
            key = (benchmark, tasks, record["mode"], record.get("threads", 1), extra)
            point_key = (key, record_method, handoff, parallelism)
            fingerprint = json.dumps(record, sort_keys=True)
            if point_key in seen:
                previous_report, previous_fingerprint = seen[point_key]
                if fingerprint != previous_fingerprint:
                    raise ValueError(
                        f"Conflicting results for {record['benchmark']}: {params} "
                        f"in {previous_report} and {report}. Select the desired reports explicitly.")
                duplicates += 1
                continue
            seen[point_key] = (report, fingerprint)
            groups[key][record_method].append((handoff, parallelism, throughput, error))
            added += 1
            parallelisms.add(parallelism)
        detail = ", ".join(map(str, sorted(parallelisms))) or "none"
        print(f"Merged {report}: {added} added, {duplicates} identical duplicates skipped, "
              f"{skipped} unrelated results skipped; added parallelism: {detail}", file=sys.stderr)
        merged_files += bool(added)
    if not groups:
        raise ValueError("No vtPerTask/vtPerWorker results with parallelism and tasksPerSlot")
    print(f"Merged total: {len(seen)} unique results from {merged_files} contributing report(s)",
          file=sys.stderr)
    return groups


def plot_groups(groups, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator, StrMethodFormatter

    output.mkdir(parents=True, exist_ok=True)
    all_points = [p for panels in groups.values() for points in panels.values() for p in points]
    handoffs = sorted({p[0] for p in all_points})
    colors = dict(COLORS)
    palette = ["#CC79A7", "#E69F00", "#56B4E9", "#000000"]
    for i, handoff in enumerate(h for h in handoffs if h not in colors):
        colors[handoff] = palette[i % len(palette)]
    xs = sorted({p[1] for p in all_points})
    ymax = max(p[2] + (p[3][1] if p[3] is not None else 0)
               for p in all_points) / THROUGHPUT_UNIT * 1.08
    fig, axes = plt.subplots(len(groups), 2, figsize=(14, 4.5 * len(groups)),
                             sharex=True, sharey=True, squeeze=False, layout="constrained")
    for row, (key, panels) in zip(axes, sorted(groups.items())):
        benchmark, tasks, mode, jmh_threads, extra = key
        for ax, method in zip(row, BENCHMARK_METHODS):
            points = panels.get(method, [])
            if not points:
                ax.text(0.5, 0.5, "no results", transform=ax.transAxes, ha="center")
            for handoff in handoffs:
                series = sorted((p for p in points if p[0] == handoff), key=lambda p: p[1])
                if not series:
                    continue
                ax.plot([p[1] for p in series], [p[2] / THROUGHPUT_UNIT for p in series],
                        marker="o", linewidth=2, color=colors[handoff], label=handoff.lower())
                errors = [p for p in series if p[3] is not None]
                if errors:
                    ax.errorbar([p[1] for p in errors], [p[2] / THROUGHPUT_UNIT for p in errors],
                                yerr=[[p[3][0] / THROUGHPUT_UNIT for p in errors],
                                      [p[3][1] / THROUGHPUT_UNIT for p in errors]],
                                fmt="none", capsize=4, color=colors[handoff], alpha=0.65)
            ax.set_xscale("log")
            ax.set_xticks(xs, labels=[str(x) for x in xs])
            ax.minorticks_off()
            ax.set_ylim(0, ymax)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=7))
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
            ax.tick_params(axis="x", bottom=True, labelbottom=True)
            ax.tick_params(axis="y", left=True, labelleft=True)
            ax.set_xlabel("parallelism (log scale)")
            ax.set_ylabel("throughput (100k tasks/s; higher is better)")
            detail = " · ".join(f"{k}={v}" for k, v in extra)
            title = f"{method} · tasks per slot = {tasks}"
            if len({(k[0], *k[2:]) for k in groups}) > 1:
                title += f"\n{benchmark} · {mode} · jmh threads={jmh_threads}"
                if detail:
                    title += f" · {detail}"
            ax.set_title(title, pad=12)
            ax.grid(True, alpha=0.2)
            ax.spines[["top", "right"]].set_visible(False)
            if points:
                ax.legend(title="handoff")
    workloads = {(k[0], *k[2:]) for k in groups}
    title = "task throughput by parallelism"
    if len(workloads) == 1:
        benchmark, mode, jmh_threads, extra = next(iter(workloads))
        detail = " · ".join(f"{k}={v}" for k, v in extra)
        title = f"{benchmark} · {detail + ' · ' if detail else ''}jmh threads={jmh_threads}"
    fig.suptitle(title, fontsize=13)
    fig.supxlabel("task throughput = batches/s × parallelism × tasks per slot. "
                  "includes executor overhead; error bars show the transformed jmh interval.",
                  fontsize=9, color="#555555")
    for extension in ("png", "svg"):
        path = output / f"tasks-throughput.{extension}"
        fig.savefig(path, dpi=180)
        print(path)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="*",
                        help="JSON reports or directories to merge "
                             "(default: all *.json in build/reports/jmh)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=ROOT / "visualization/plots/tasks",
                        help="Output directory (default: visualization/plots/tasks)")
    args = parser.parse_args()
    try:
        groups = load_groups(args.reports or [ROOT / "build/reports/jmh"])
        plot_groups(groups, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
