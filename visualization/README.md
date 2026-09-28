# JMH visualization

From the project root, run `uv run visualization/plot_jmh.py`, `uv run visualization/plot_parknanos.py`, or `uv run visualization/plot_parkstackdepth.py` for task, parkNanos, or stack-depth benchmarks, respectively.
All read `build/reports/jmh/results.json` and export PNG/SVG charts into matching `tasks/`, `parknanos/`, or `parkstackdepth/` subfolders of `visualization/plots/`; append a report path and `--output-dir path/to/plots` to override the defaults.
The stack-depth plot accepts a second report path containing the `StartEndBenchmark` result and draws its cost as a horizontal reference line; it defaults to `visualization/results-start-end.json`.
