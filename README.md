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
# Full run: benchmark annotations apply, with JMH defaults for unspecified settings
./gradlew jmh

# Quick setup check: 1 warmup and 1 measurement, 100 ms each, 1 fork
./gradlew jmh -PjmhSmoke=true

# Compile and package benchmarks without running them
./gradlew jmhJar
```

Results are written to `build/reports/jmh/results.json`.

Run `./gradlew jmh -Pbenchmark=ParkStackDepth` to compare virtual-thread parking
at 0, 16, 64, 256, and 1024 extra recursive frames.
Each frame keeps eight `Long` locals live across the recursive call and park,
then passes them to a non-inlined checksum method.
`park` calls `LockSupport.park()` at the deepest frame; a dedicated platform
thread waits until that virtual thread is parked, then calls `unpark()`.
`baseline` follows the same recursion without parking; both have a spinning
helper, created and joined outside measurements. Their difference estimates
parking/resuming costs, including helper polling, scheduling, and stack freezing/thawing.
Both use virtual JMH workers, excluding thread creation, with one warmup and
three measurement iterations; recursion is not inlined and unwinds fully after
each call. Depth is a proxy for stack size, not a byte count, and this benchmark
does not isolate stack-copy time.

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

### Findings: parking, thread creation, and queue handoffs

The saved [stack-depth results](visualization/results-park-stack-depth.json)
measure **1.671 ± 0.102 µs/op** for `park` at depth 0, with a baseline of
about 0.003 µs/op. The saved [start/end results](visualization/results-start-end.json)
measure **6.422 ± 0.184 µs/op** for creating a virtual thread and joining it.
Errors are JMH's reported 99.9% confidence intervals. Depth 0 means no extra
recursive calls, not an empty stack. The parking benchmark reuses a virtual
thread and has a dedicated platform thread spinning to unpark it immediately;
these timings are specific to that setup.

This does not imply that reused workers must outperform a fresh virtual thread
per task. `TasksBenchmark.vtPerWorker` adds a queue handoff and creates and stops
its workers inside each batch. At one task per slot there is no reuse benefit.
The task charts divide batch elapsed time by task count, so concurrent work
overlaps: their ns/task values are not individual task latencies.

An available lock does not inherently require suspending a virtual thread.
Waiting on an empty queue does involve a condition wait: release the lock,
wait, and reacquire the lock before returning. `signal()` transfers a waiter
from the condition queue to the lock's acquisition queue; it does not immediately
hand execution to the consumer. See the
[JDK 26 ConditionObject documentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html).
In this benchmark, each replacement task is submitted only after the coordinator
receives a completion, so the worker may wait again between tasks.

**Working hypothesis:** the full queue handoff, including scheduling and
synchronization, is costly relative to the tiny task. We have not established
that `ReentrantLock.lock()` itself explains the performance difference.
A useful next experiment is to compare direct park/unpark, condition
await/signal, and queue add/take under matching conditions.

Further reading (reviewed September 2026):

- [Adam Warski — Limits of Loom's performance (2023)](https://softwaremill.com/limits-of-looms-performance/):
  repeated virtual-thread handoffs were highly sensitive to waiting strategy
  and scheduler parallelism. One implementation improved from roughly 17.5 s
  to 5.1 s with one carrier, followed by further improvements. Historical
  workload-specific measurements, not expected JDK 26 timings.
- [SoftwareMill — Announcing jox: Fast and Scalable Channels in Java (2023)](https://softwaremill.com/announcing-jox-fast-and-scalable-channels-in-java/):
  JMH comparisons include `ArrayBlockingQueue`, `SynchronousQueue`, and
  `Exchanger` on virtual threads, with substantial variability and discussion
  of scheduling effects.
- [Francesco Nigro — To Cache or Not to Cache Virtual Threads (revised September 2026)](https://quarkus.io/blog/to-cache-or-not-to-cache-virtual-threads/):
  pooling reduced allocations but improved throughput by only about 3% with a
  4 GB heap and approximately matched unpooled throughput at 1 GB. The revision
  retracts an earlier causal explanation after finding a benchmark bug;
  allocation savings alone do not predict throughput improvements.

Configuration references: [kotlinx-coroutines](https://github.com/Kotlin/kotlinx.coroutines)
and the [JMH Gradle plugin](https://github.com/melix/jmh-gradle-plugin).
