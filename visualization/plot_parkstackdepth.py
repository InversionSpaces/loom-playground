#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Plot ParkStackDepthBenchmark park, baseline and their difference against stack depth."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERIES = {
    "park": ("Park + recursion", "#0072B2", "o"),
    "baseline": ("Baseline: recursion only", "#D55E00", "s"),
}
NANOSECONDS = {"ns/op": 1, "us/op": 1_000, "ms/op": 1_000_000,
               "s/op": 1_000_000_000, "min/op": 60_000_000_000,
               "hr/op": 3_600_000_000_000}


def load_groups(report):
    groups = defaultdict(list)
    for record in json.loads(report.read_text()):
        benchmark, _, method = record["benchmark"].rpartition(".")
        if benchmark.split(".")[-1] != "ParkStackDepthBenchmark" or method not in SERIES:
            continue
        metric = record["primaryMetric"]
        unit = metric["scoreUnit"]
        if record["mode"] not in {"avgt", "ss", "sample"} or unit not in NANOSECONDS:
            raise ValueError(f"Expected time/op scores, got {record['mode']} {unit}")
        factor = NANOSECONDS[unit]
        score = float(metric["score"]) * factor
        error = float(metric.get("scoreError", "NaN")) * factor
        if not math.isfinite(error) or error < 0:
            error = None
        params = record["params"]
        extra = tuple(sorted((k, str(v)) for k, v in params.items() if k != "stackDepth"))
        key = (benchmark, record["mode"], unit, record.get("threads", 1), extra)
        groups[key].append((method, int(params["stackDepth"]), score, error))
    if not groups:
        raise ValueError("No ParkStackDepthBenchmark results found")
    return groups


def plot_groups(groups, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    output.mkdir(parents=True, exist_ok=True)
    for key, points in sorted(groups.items()):
        fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
        for method, (label, color, marker) in SERIES.items():
            series = sorted((p for p in points if p[0] == method), key=lambda p: p[1])
            if not series:
                continue
            ax.plot([p[1] for p in series], [p[2] for p in series],
                    label=label, color=color, marker=marker, linewidth=2)
            errors = [p for p in series if p[3] is not None]
            if errors:
                ax.errorbar([p[1] for p in errors], [p[2] for p in errors],
                            yerr=[p[3] for p in errors], fmt="none", capsize=4,
                            color=color, alpha=0.7)

        park = {depth: score for method, depth, score, _ in points if method == "park"}
        baseline = {depth: score for method, depth, score, _ in points if method == "baseline"}
        depths = sorted(park.keys() & baseline.keys())
        if depths:
            ax.plot(depths, [park[depth] - baseline[depth] for depth in depths],
                    label="Park − baseline", color="#009E73", marker="^",
                    linestyle="--", linewidth=2)

        ax.set_xlabel("Stack depth (additional recursive calls)")
        ax.set_ylabel("Time per operation (ns)")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True))
        compact = FuncFormatter(lambda value, _: f"{value / 1_000:g}k"
                                if abs(value) >= 1_000 else f"{value:g}")
        ax.xaxis.set_major_formatter(compact)
        ax.yaxis.set_major_formatter(compact)
        ax.axhline(0, color="#999999", linewidth=0.8, zorder=1)
        ax.grid(True, alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left")

        benchmark, mode, unit, threads, extra = key
        detail = " · ".join(f"{k}={v}" for k, v in extra)
        ax.set_title(f"{benchmark}\nMode={mode} · JMH threads={threads}"
                     + (f" · {detail}" if detail else ""), fontsize=13)
        fig.supxlabel("Park includes recursion, suspension, helper-thread unpark and resumption.\n"
                      "Error bars: ± JMH scoreError (99.9% CI), when available; difference has no error bars.",
                      fontsize=9, color="#555555")
        suffix = "" if len(groups) == 1 else "-" + hashlib.sha256(repr(key).encode()).hexdigest()[:8]
        for extension in ("png", "svg"):
            path = output / f"parkstackdepth{suffix}.{extension}"
            fig.savefig(path, dpi=180)
            print(path)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?",
                        default=ROOT / "build/reports/jmh/results.json",
                        help="JMH JSON report (default: build/reports/jmh/results.json)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=ROOT / "visualization/plots/parkstackdepth",
                        help="Output directory (default: visualization/plots/parkstackdepth)")
    args = parser.parse_args()
    try:
        plot_groups(load_groups(args.report), args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
