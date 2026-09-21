#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Compare virtual and platform thread ParkNanosBenchmark results in ns/call."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
COLORS = {"Virtual": "#0072B2", "Platform": "#D55E00"}
NANOSECONDS = {"ns/op": 1, "us/op": 1_000, "ms/op": 1_000_000,
               "s/op": 1_000_000_000, "min/op": 60_000_000_000,
               "hr/op": 3_600_000_000_000}


def load_groups(report):
    records = json.loads(report.read_text())
    if not isinstance(records, list):
        raise ValueError("Expected a JMH JSON array of benchmark results")
    groups = defaultdict(list)
    seen = set()
    skipped = 0
    for record in records:
        benchmark = record["benchmark"]
        if benchmark.split(".")[-2:] != ["ParkNanosBenchmark", "bench"]:
            skipped += 1
            continue
        params = record["params"]
        parking_time = int(params["parkingTime"])
        thread_type = params["threadType"]
        if parking_time < 0 or thread_type not in COLORS:
            raise ValueError(f"Invalid ParkNanosBenchmark parameters: {params}")
        metric = record["primaryMetric"]
        unit = metric["scoreUnit"]
        if record["mode"] not in {"avgt", "ss", "sample"} or unit not in NANOSECONDS:
            raise ValueError(f"Expected time/op scores, got {record['mode']} {unit}")
        # JMH already applies @OperationsPerInvocation(10_000).
        factor = NANOSECONDS[unit]
        score = float(metric["score"]) * factor
        if not math.isfinite(score) or score <= 0:
            raise ValueError("ParkNanos plots require finite, positive scores")
        try:
            error = float(metric.get("scoreError", "NaN")) * factor
        except (ValueError, TypeError):
            error = math.nan
        if not math.isfinite(error) or not 0 <= error < score:
            error = None
        extra = tuple(sorted((k, str(v)) for k, v in params.items()
                             if k not in {"parkingTime", "threadType"}))
        key = (benchmark, record["mode"], unit, record.get("threads", 1), extra)
        point_key = (key, thread_type, parking_time)
        if point_key in seen:
            raise ValueError(f"Duplicate result for {benchmark}: {params}")
        seen.add(point_key)
        groups[key].append((thread_type, parking_time, score, error))
    if not groups:
        raise ValueError("No ParkNanosBenchmark.bench results found")
    if skipped:
        print(f"Skipped {skipped} unrelated result(s).", file=sys.stderr)
    return groups


def plot_groups(groups, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    output.mkdir(parents=True, exist_ok=True)
    for key, points in sorted(groups.items()):
        positive = [p for p in points if p[1] > 0]
        panels = [(points, "All requested durations", True)]
        if positive:
            panels.append((positive, "Positive requested durations", False))
        fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 5.5),
                                 squeeze=False, layout="constrained")
        for ax, (subset, title, logarithmic) in zip(axes[0], panels):
            for thread_type, color in COLORS.items():
                series = sorted((p for p in subset if p[0] == thread_type),
                                key=lambda p: p[1])
                if not series:
                    continue
                ax.plot([p[1] for p in series], [p[2] for p in series],
                        marker="o" if thread_type == "Virtual" else "s",
                        linewidth=2, color=color, label=thread_type)
                errors = [p for p in series if p[3] is not None]
                if errors:
                    ax.errorbar([p[1] for p in errors], [p[2] for p in errors],
                                yerr=[p[3] for p in errors], fmt="none",
                                capsize=4, color=color, alpha=0.7)
            xs = sorted({p[1] for p in subset})
            if 0 in xs:
                ax.set_xscale("symlog", linthresh=1, linscale=0.5)
            else:
                ax.set_xscale("log")
            if logarithmic:
                ax.set_yscale("log")
            else:
                ax.set_ylim(bottom=0)
            positive_xs = [x for x in xs if x > 0]
            if positive_xs:
                # Sample densely so y=x stays accurate on nonlinear axes.
                # The origin cannot be displayed on the logarithmic y-axis.
                start, end = positive_xs[0], positive_xs[-1]
                ideal = [start * (end / start) ** (i / 255) for i in range(256)]
                ax.plot(ideal, ideal, color="#555555", linestyle="--",
                        linewidth=1.5, marker="." if start == end else None,
                        label="Ideal: elapsed = requested (y = x)", zorder=1)
            ax.set_xticks(xs, labels=[f"{x:,}" for x in xs])
            ax.minorticks_off()
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.4g}"))
            ax.set_xlabel("Requested park duration (ns; log spacing above 1 ns)")
            ax.set_ylabel("Elapsed time per call (ns/call" +
                          (", log scale)" if logarithmic else ")"))
            ax.set_title(title)
            ax.grid(True, alpha=0.2)
            ax.spines[["top", "right"]].set_visible(False)
            ax.legend()

        benchmark, mode, unit, threads, extra = key
        detail = " · ".join(f"{k}={v}" for k, v in extra)
        fig.suptitle(f"{benchmark}\nMode={mode} · JMH threads={threads}"
                     + (f" · {detail}" if detail else ""), fontsize=13)
        fig.supxlabel("JMH time/op converted to ns/call; already normalized by operations per invocation.\n"
                      "Includes amortized thread creation/start/join. Error bars: JMH score ± scoreError.",
                      fontsize=9, color="#555555")
        suffix = "" if len(groups) == 1 else "-" + hashlib.sha256(repr(key).encode()).hexdigest()[:8]
        for extension in ("png", "svg"):
            path = output / f"parknanos{suffix}.{extension}"
            fig.savefig(path, dpi=180)
            print(path)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?",
                        default=ROOT / "build/reports/jmh/results.json",
                        help="JMH JSON report (default: build/reports/jmh/results.json)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=ROOT / "visualization/plots/parknanos",
                        help="Output directory (default: visualization/plots/parknanos)")
    args = parser.parse_args()
    try:
        plot_groups(load_groups(args.report), args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
