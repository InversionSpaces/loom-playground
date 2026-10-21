# Coroutines and Project Loom

Kotlin/JVM experiments with virtual threads, kotlinx-coroutines, Jox channels,
and JMH. Requires JDK 26; Gradle can download the toolchain automatically.

## Build and run

```sh
./gradlew build
./gradlew run
```

The demo runs a coroutine on a virtual-thread-backed dispatcher.

## Benchmarks

```sh
./gradlew jmh -Pbenchmark=TasksBenchmark
./gradlew jmh -Pbenchmark=ParkNanosBenchmark
./gradlew jmh -Pbenchmark=ParkStackDepthBenchmark
./gradlew jmh -Pbenchmark=StartEndBenchmark
```

Use `./gradlew jmh` to run all benchmarks, add `-PjmhSmoke=true` for a setup
check, or use `./gradlew jmhJar` to package benchmarks without running them.
Results go to `build/reports/jmh/results.json`.

`TasksBenchmark` compares a virtual thread per task with reused virtual-thread
workers. `QUEUE` uses an `ArrayBlockingQueue` per worker and a shared
`LinkedBlockingQueue` for completions. `JOX` uses buffered Jox channels;
`JOX_TRY` tries non-blocking operations before falling back to blocking ones.
Each completion carries the slot and result; the coordinator submits replacement
work to that slot, keeping at most `parallelism` tasks in flight. Measurements
include executor creation and shutdown. JMH reports batches/s; each batch contains
`parallelism * tasksPerSlot` tasks.

`ParkNanosBenchmark` measures requested versus elapsed parking time.
`ParkStackDepthBenchmark` measures parking at different recursive stack depths
against a recursion-only baseline, including helper-thread and scheduler overhead.
`StartEndBenchmark` measures virtual-thread creation and joining.

## Visualization

```sh
uv run visualization/plot_jmh.py
uv run visualization/plot_parknanos.py
uv run visualization/plot_parkstackdepth.py
```

See [visualization/README.md](visualization/README.md) for report merging,
chart units, and output locations.
