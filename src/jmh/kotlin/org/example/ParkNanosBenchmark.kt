package org.example

import java.util.concurrent.TimeUnit
import org.openjdk.jmh.annotations.Benchmark
import org.openjdk.jmh.annotations.BenchmarkMode
import org.openjdk.jmh.annotations.Mode
import org.openjdk.jmh.annotations.OperationsPerInvocation
import org.openjdk.jmh.annotations.OutputTimeUnit
import org.openjdk.jmh.annotations.Param
import org.openjdk.jmh.annotations.Scope
import org.openjdk.jmh.annotations.State
import java.util.concurrent.ExecutorCompletionService
import java.util.concurrent.locks.LockSupport

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
open class ParkNanosBenchmark {

    @Param("0", "1", "10", "100", "1000")
    @JvmField
    var parkingTime: Long = 0

    @Benchmark
    @OperationsPerInvocation(1000)
    fun bench() {
        Thread.ofVirtual().start {
            repeat(1000) {
                LockSupport.parkNanos(parkingTime)
            }
        }.join()
    }
}
