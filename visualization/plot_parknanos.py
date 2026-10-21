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
BENCHMARK_METHODS = {"virtual": "Virtual", "platform": "Platform"}
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
        benchmark_class, _, method = benchmark.rpartition(".")
        if (benchmark_class.split(".")[-1] != "ParkNanosBenchmark"
                or method not in BENCHMARK_METHODS):
            skipped += 1
            continue
        params = record["params"]
        parking_time = int(params["parkingTime"])
        thread_type = BENCHMARK_METHODS[method]
        benchmark = benchmark_class
        if parking_time < 0 or thread_type not in COLORS:
            raise ValueError(f"Invalid ParkNanosBenchmark parameters: {params}")
        metric = record["primaryMetric"]
        unit = metric["scoreUnit"]
        if record["mode"] not in {"avgt", "ss", "sample"} or unit not in NANOSECONDS:
            raise ValueError(f"Expected time/op scores, got {record['mode']} {unit}")
        # Each benchmark invocation performs one park.
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
                             if k != "parkingTime"))
        key = (benchmark, record["mode"], unit, record.get("threads", 1), extra)
        point_key = (key, thread_type, parking_time)
        if point_key in seen:
            raise ValueError(f"Duplicate result for {benchmark}: {params}")
        seen.add(point_key)
        groups[key].append((thread_type, parking_time, score, error))
    if not groups:
        raise ValueError("No ParkNanosBenchmark results found")
    if skipped:
        print(f"Skipped {skipped} unrelated result(s).", file=sys.stderr)
    return groups


def plot_groups(groups, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import FixedLocator, FuncFormatter, MultipleLocator

    # Continuous, invertible linear sections retain actual ns tick values.
    transition = 10_000
    compression = 10

    def compress(values):
        values = np.asarray(values)
        return np.where(values <= transition, values,
                        transition + (values - transition) / compression)

    def expand(values):
        values = np.asarray(values)
        return np.where(values <= transition, values,
                        transition + (values - transition) * compression)

    output.mkdir(parents=True, exist_ok=True)
    for key, points in sorted(groups.items()):
        fig, (ax, difference_ax) = plt.subplots(1, 2, figsize=(16, 6),
                                               layout="constrained")
        # Preserve log spacing while showing zero durations.
        for target in (ax, difference_ax):
            target.set_xscale("symlog", linthresh=1, linscale=0.5)
        ax.set_yscale("symlog", linthresh=1, linscale=0.5)
        difference_ax.set_yscale("function", functions=(compress, expand))
        difference_ax.yaxis.set_major_locator(MultipleLocator(10_000))
        for thread_type, color in COLORS.items():
            series = sorted((p for p in points if p[0] == thread_type),
                            key=lambda p: p[1])
            if not series:
                continue
            marker = "o" if thread_type == "Virtual" else "s"
            ax.plot([p[1] for p in series], [p[2] for p in series],
                    marker=marker, linewidth=2, color=color,
                    label=f"{thread_type.lower()}: elapsed")
            difference_ax.plot([p[1] for p in series], [p[2] - p[1] for p in series],
                    marker=marker, markerfacecolor="none", linestyle=":",
                    linewidth=2, color=color,
                    label=f"{thread_type.lower()}: elapsed − requested")
            errors = [p for p in series if p[3] is not None]
            if errors:
                # Subtracting an exact duration leaves the error width unchanged.
                for target, difference in ((ax, False), (difference_ax, True)):
                    target.errorbar([p[1] for p in errors],
                                [p[2] - (p[1] if difference else 0) for p in errors],
                                yerr=[p[3] for p in errors], fmt="none",
                                capsize=4, color=color, alpha=0.7)

        xs = sorted({p[1] for p in points})
        difference_ax.axhline(0, color="#999999", linewidth=0.8, zorder=1)
        difference_ax.axhline(transition, color="#777777", linestyle="--",
                              linewidth=0.8, zorder=1)
        # Dense samples keep y=x accurate through the linear/log transition.
        ideal = [i / 32 for i in range(33)] if xs[0] == 0 and xs[-1] > 0 else []
        if xs[-1] > 0:
            start, end = max(1, xs[0]), xs[-1]
            ideal.extend(start * (end / start) ** (i / 255) for i in range(256))
        else:
            ideal = [0]
        ax.plot(ideal, ideal, color="#555555", linestyle="--", linewidth=1.5,
                marker="." if xs[0] == xs[-1] else None,
                label="ideal: elapsed = requested (y = x)", zorder=1)
        ax.set_ylabel("time per call (ns; symmetric log scale)")
        difference_ax.set_ylabel("elapsed − requested (ns; linear sections)\n"
                                 "10× compression above 10,000 ns")
        ax.set_title("elapsed time")
        difference_ax.set_title("elapsed − requested")
        for target in (ax, difference_ax):
            target.set_xticks(xs, labels=[f"{x / 1_000:g}k" if x >= 1_000 else str(x)
                                         for x in xs],
                              rotation=45, ha="right", rotation_mode="anchor", fontsize=9)
            target.minorticks_off()
            target.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
            target.set_xlabel("requested park duration (ns; log spacing above 1 ns)")
            target.grid(True, alpha=0.2)
            target.spines[["top", "right"]].set_visible(False)
            target.legend(loc="upper left")

        difference_ax.yaxis.set_minor_locator(FixedLocator(range(1_000, 10_000, 1_000)))
        difference_ax.yaxis.set_minor_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
        difference_ax.tick_params(axis="y", which="minor", labelsize=8)
        difference_ax.grid(True, axis="y", which="minor", alpha=0.12)

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
