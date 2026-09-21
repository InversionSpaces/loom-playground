# JMH visualization

From the project root, run:

```sh
uv run visualization/plot_jmh.py
```

The script declares its Matplotlib dependency, which `uv` installs automatically.
Alternatively, install `matplotlib>=3.9,<4` in a Python environment and run
`python visualization/plot_jmh.py`.

The benchmark parameters are `parallelism` (maximum tasks in flight) and
`tasksPerSlot` (batch size divided by parallelism).
The script pairs the `vtPerTask` and `vtPerWorker` benchmark methods from the same
class and workload. Reports must use these methods and parameter names.

By default it reads `build/reports/jmh/results.json` and saves one PNG and SVG
per `parallelism` in `visualization/plots/`, plus `combined.png` and `combined.svg`.
The combined ratio chart has one line
per parallelism level, distinguished by color and marker. Different workloads get
separate ratio files with unique suffixes. It also works from another working
directory. To choose a report or destination:

```sh
uv run visualization/plot_jmh.py path/to/results.json --output-dir path/to/plots
```

- Ratio chart: `VT-PER-TASK cost / VT-PER-WORKER cost`, on a linear y-axis.
  A dashed line marks `1×` (equal cost). Below it, fresh threads cost less;
  above it, reused workers cost less. Each ratio pairs the same workload,
  parallelism and tasks per slot. Both executors must be present at every task count.
  Ratios use point estimates; no ratio confidence intervals are inferred.
- X-axis in all charts: `tasksPerSlot`, sorted numerically on a logarithmic scale.
- The following settings apply to the individual absolute-cost charts:
- Y-axis: elapsed nanoseconds per task (lower is better), on a logarithmic scale
  starting at 1 ns/task. All charts share the same limits and 10 labeled ticks
  in geometric progression, including room for error bars.
- Blue: `VT-PER-TASK`; orange: `VT-PER-WORKER`, consistent across graphs.
- Error bars: transformed JMH `score ± scoreError` bounds. Unavailable intervals
  and intervals reaching zero are omitted.

For the current `TasksBenchmark`, `ops/s` means **whole batches per second**.
Each batch executes `parallelism * tasksPerSlot` tasks. The plotted cost is
`1_000_000_000 / (score * parallelism * tasksPerSlot)` nanoseconds per task.
Average-time and single-shot scores are converted to nanoseconds and divided
by the same task count. Throughput error bars become asymmetric after inversion.

This is elapsed batch time divided by completed tasks, including executor setup,
submission, collection and shutdown. With concurrent tasks, it is not individual
task latency or CPU time. Normalization assumes one JMH operation is one batch;
do not also apply `@OperationsPerInvocation` or `-opi` to normalize those tasks.

Other parameters (such as `complexity`), benchmark names, modes, units and JMH
worker counts get separate graphs so different workloads are not mixed.
Unrelated methods and results missing the two required parameters are skipped; duplicate points
are rejected instead of silently combined.
