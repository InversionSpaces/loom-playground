#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Plot ParkStackDepthBenchmark costs against stack depth and a start/end reference."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERIES = {
    "park": ("park + recursion", "#0072B2", "o"),
    "baseline": ("baseline: recursion only", "#D55E00", "s"),
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


def load_start_end_cost(report):
    costs = []
    for record in json.loads(report.read_text()):
        benchmark, _, method = record["benchmark"].rpartition(".")
        if benchmark.split(".")[-1] != "StartEndBenchmark" or method != "bench":
            continue
        metric = record["primaryMetric"]
        unit = metric["scoreUnit"]
        if record["mode"] not in {"avgt", "ss", "sample"} or unit not in NANOSECONDS:
            raise ValueError(f"Expected StartEndBenchmark time/op scores, got {record['mode']} {unit}")
        score = float(metric["score"]) * NANOSECONDS[unit]
        if not math.isfinite(score) or score < 0:
            raise ValueError("StartEndBenchmark requires a finite, non-negative score")
        costs.append(score)
    if not costs:
        raise ValueError("No StartEndBenchmark.bench result found")
    if len(costs) != 1:
        raise ValueError(f"Expected one StartEndBenchmark.bench result, found {len(costs)}")
    return costs[0]


def plot_groups(groups, start_end_cost, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

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
        differences = [park[depth] - baseline[depth] for depth in depths]
        if depths:
            ax.plot(depths, differences,
                    label="park - baseline", color="#009E73", marker="^",
                    linestyle="--", linewidth=2)
            for i, (depth, difference) in enumerate(zip(depths, differences)):
                last = i == len(depths) - 1
                offset = (-8, -28) if last else ((0, -16) if i >= len(depths) - 3 else (8, -12))
                alignment = "right" if last else ("center" if i >= len(depths) - 3 else "left")
                ax.annotate(f"{difference:,.0f} ns", xy=(depth, difference),
                            xytext=offset,
                            textcoords="offset points",
                            ha=alignment, va="top",
                            color="#009E73", fontsize=9)

        ax.axhline(start_end_cost, label="Virtual Thread start + join",
                   color="#CC79A7", linestyle=":", linewidth=2)
        ax.annotate(f"{start_end_cost:,.0f} ns", xy=(0.02, start_end_cost),
                    xycoords=("axes fraction", "data"), xytext=(0, 6),
                    textcoords="offset points", va="bottom",
                    color="#CC79A7", fontsize=9)

        ax.set_xlabel("stack depth (linear 0–16, log above 16)")
        ax.set_ylabel("time per operation (ns; log scale)")
        ax.set_yscale("log")
        # Preserve the zero-depth measurement, which a pure log axis cannot show.
        ax.set_xscale("symlog", linthresh=16)
        ax.set_xticks(sorted({p[1] for p in points}))
        ax.set_xlim(left=0)
        compact = FuncFormatter(lambda value, _: f"{value / 1_000:.4g}k"
                                if abs(value) >= 1_000 else f"{value:.4g}")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.yaxis.set_major_formatter(compact)
        ax.grid(True, alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left")

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
    parser.add_argument("start_end_report", type=Path, nargs="?",
                        default=ROOT / "visualization/results-start-end.json",
                        help="StartEndBenchmark JMH JSON report "
                             "(default: visualization/results-start-end.json)")
    parser.add_argument("-o", "--output-dir", type=Path,
                        default=ROOT / "visualization/plots/parkstackdepth",
                        help="Output directory (default: visualization/plots/parkstackdepth)")
    args = parser.parse_args()
    try:
        plot_groups(load_groups(args.report), load_start_end_cost(args.start_end_report),
                    args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
