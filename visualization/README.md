# JMH visualization

Run from the project root:

```sh
uv run visualization/plot_jmh.py
uv run visualization/plot_parknanos.py
uv run visualization/plot_parkstackdepth.py
```

PNG/SVG charts go to matching subfolders of `visualization/plots/`.
Pass report paths and `--output-dir PATH` to override defaults.

The task script merges all JSON reports in `build/reports/jmh`, logs its inputs,
skips empty files and identical duplicates, and rejects conflicting results.
It plots both methods in one image, with rows by tasks per slot and lines by
handoff. Throughput is `batches/s × parallelism × tasksPerSlot`, displayed in
100k tasks/s units with JMH error bars.

The park scripts read `build/reports/jmh/results.json`. Stack-depth also accepts
a second report for the start/end reference line (default:
`visualization/results-start-end.json`).
