package org.example

import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.LockSupport
import org.openjdk.jmh.annotations.Benchmark
import org.openjdk.jmh.annotations.BenchmarkMode
import org.openjdk.jmh.annotations.CompilerControl
import org.openjdk.jmh.annotations.Fork
import org.openjdk.jmh.annotations.Level
import org.openjdk.jmh.annotations.Measurement
import org.openjdk.jmh.annotations.Mode
import org.openjdk.jmh.annotations.OutputTimeUnit
import org.openjdk.jmh.annotations.Param
import org.openjdk.jmh.annotations.Scope
import org.openjdk.jmh.annotations.Setup
import org.openjdk.jmh.annotations.State
import org.openjdk.jmh.annotations.TearDown
import org.openjdk.jmh.annotations.Warmup

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 1, time = 1)
@Measurement(iterations = 3, time = 1)
@Fork(jvmArgsAppend = ["-Djmh.executor=VIRTUAL"])
open class ParkStackDepthBenchmark {
    @Param("0", "16", "64", "256", "1024", "4096")
    @JvmField
    var stackDepth: Int = 0

    @Volatile
    private var payload: Long = 1

    @Volatile
    private var running = false

    @Volatile
    private var parkRequested = false

    private var unparker: Thread? = null

    @Setup(Level.Trial)
    fun setup() {
        check(Thread.currentThread().isVirtual) { "Requires a virtual JMH worker; check fork settings" }
        val worker = Thread.currentThread()
        parkRequested = false
        running = true
        unparker = Thread.ofPlatform().daemon(true).name("stack-depth-unparker").start {
            while (running) {
                if (parkRequested && LockSupport.getBlocker(worker) === this &&
                    worker.state == Thread.State.WAITING
                ) {
                    parkRequested = false
                    LockSupport.unpark(worker)
                } else {
                    Thread.onSpinWait()
                }
            }
        }
    }

    @TearDown(Level.Trial)
    fun teardown() {
        running = false
        unparker?.join()
        unparker = null
    }

    @Benchmark
    fun park(): Long = parkAtDepth(stackDepth, true)

    @Benchmark
    fun baseline(): Long = parkAtDepth(stackDepth, false)

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    fun parkAtDepth(remaining: Int, shouldPark: Boolean): Long {
        val a = payload
        val b = payload
        val c = payload
        val d = payload
        val e = payload
        val f = payload
        val g = payload
        val h = payload
        val result = if (remaining == 0) {
            if (shouldPark) {
                parkRequested = true
                do {
                    LockSupport.park(this)
                } while (parkRequested)
            }
            1L
        } else {
            parkAtDepth(remaining - 1, shouldPark) + remaining
        }
        return consumeLocals(result, a, b, c, d, e, f, g, h)
    }

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    fun consumeLocals(
        result: Long, a: Long, b: Long, c: Long, d: Long,
        e: Long, f: Long, g: Long, h: Long
    ): Long =
        result + a + b + c + d + e + f + g + h
}
