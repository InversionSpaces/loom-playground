package org.example

import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.LockSupport
import org.openjdk.jmh.annotations.Benchmark
import org.openjdk.jmh.annotations.BenchmarkMode
import org.openjdk.jmh.annotations.Fork
import org.openjdk.jmh.annotations.Level
import org.openjdk.jmh.annotations.Measurement
import org.openjdk.jmh.annotations.Mode
import org.openjdk.jmh.annotations.OutputTimeUnit
import org.openjdk.jmh.annotations.Param
import org.openjdk.jmh.annotations.Scope
import org.openjdk.jmh.annotations.Setup
import org.openjdk.jmh.annotations.State
import org.openjdk.jmh.annotations.Warmup
import org.openjdk.jmh.infra.BenchmarkParams

// macOS timer coalescing can increase parkNanos wakeup delays for both thread types.
// Disable system-wide for comparison: sudo sysctl -w kern.timer.coalescing_enabled=0
// Restore afterward: sudo sysctl -w kern.timer.coalescing_enabled=1
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 1)
@Measurement(iterations = 3, time = 15)
open class ParkNanosBenchmark {

    @Param("0", "1", "100", "1000", "10000", "1000000", "10000000")
    @JvmField
    var parkingTime: Long = 0

    @Setup(Level.Trial)
    fun verifyWorker(params: BenchmarkParams) {
        val expectVirtual = params.benchmark.endsWith(".virtual")
        check(Thread.currentThread().isVirtual == expectVirtual) {
            "${params.benchmark} requires a ${if (expectVirtual) "virtual" else "platform"} JMH worker; check fork settings"
        }
    }

    @Benchmark
    @Fork(jvmArgsAppend = ["-Djmh.executor=VIRTUAL"])
    fun virtual() {
        LockSupport.parkNanos(parkingTime)
    }

    @Benchmark
    @Fork(jvmArgsAppend = ["-Djmh.executor=PLATFORM"])
    fun platform() {
        LockSupport.parkNanos(parkingTime)
    }
}
