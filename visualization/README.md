# JMH visualization

From the project root, run `uv run visualization/plot_jmh.py` for task benchmarks or `uv run visualization/plot_parknanos.py` for parkNanos benchmarks.
Both read `build/reports/jmh/results.json` and export PNG/SVG charts to `visualization/plots/tasks/` and `visualization/plots/parknanos/`, respectively; append a report path and `--output-dir path/to/plots` to override the defaults.
