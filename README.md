# Coroutines and Project Loom

Kotlin/JVM project using a JDK 26 toolchain, kotlinx-coroutines 1.11.0,
and JMH 1.37 via the JMH Gradle plugin 0.7.3.

## Build and run

Use the checked-in Gradle wrapper. Gradle detects an installed JDK 26, or the
Foojay toolchain resolver downloads one when needed. Dependency and toolchain
downloads require network access on the first build.

```sh
./gradlew build
./gradlew run
```

The demo runs a coroutine on a virtual-thread-backed dispatcher and checks that
it is executing on a virtual thread. The dispatcher is closed afterward.
Virtual threads do not require preview flags.

## Benchmarks

Put Kotlin benchmarks in `src/jmh/kotlin` (Java benchmarks can use `src/jmh/java`).
JMH uses the project's JDK 26 toolchain, including forked benchmark JVMs.

```sh
# Full run: 3 warmup iterations, 5 measurement iterations, 1 second each, 2 forks
./gradlew jmh

# Quick setup check: 1 warmup and 1 measurement, 100 ms each, 1 fork
./gradlew jmh -PjmhSmoke=true

# Compile and package benchmarks without running them
./gradlew jmhJar
```

Results are written to `build/reports/jmh/results.json`.

Plot the report with `uv run visualization/plot_jmh.py`. See
[visualization/README.md](visualization/README.md) for options and score units.

`TasksBenchmark` compares a fresh virtual thread per task with dedicated
virtual-thread workers through two benchmark methods: `vtPerTask` and `vtPerWorker`.
Each reused worker runs a small `take()`/`run()` loop on
its own `ArrayBlockingQueue`, without a `ThreadPoolExecutor`. A shared completion
queue identifies the finished slot, and
the next task is submitted to that same slot only after completion. Both modes
use this completion protocol and allow at most `parallelism` tasks in flight.
All workers receive a stop marker before waiting for termination. A single
virtual-thread-per-task executor manages thread lifetimes in both modes.
Each invocation executes `parallelism * tasksPerSlot`
tasks, waits for every task, and returns a sum consumed by JMH. Executor creation
and shutdown are included in measurement. Throughput is reported as whole batches
per second, including submission and result collection, not individual tasks.
Smoke-run scores only verify that the harness works. Adapt the workload and use
full runs before drawing performance conclusions.

Configuration references: [kotlinx-coroutines](https://github.com/Kotlin/kotlinx.coroutines)
and the [JMH Gradle plugin](https://github.com/melix/jmh-gradle-plugin).
