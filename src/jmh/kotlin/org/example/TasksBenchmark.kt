package org.example

import com.softwaremill.jox.Channel
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.BlockingQueue
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import org.openjdk.jmh.annotations.Benchmark
import org.openjdk.jmh.annotations.BenchmarkMode
import org.openjdk.jmh.annotations.Fork
import org.openjdk.jmh.annotations.Measurement
import org.openjdk.jmh.annotations.Mode
import org.openjdk.jmh.annotations.OutputTimeUnit
import org.openjdk.jmh.annotations.Param
import org.openjdk.jmh.annotations.Scope
import org.openjdk.jmh.annotations.State
import org.openjdk.jmh.annotations.Warmup

@State(Scope.Benchmark)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Fork(2)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
open class TasksBenchmark {
    @Param("1", "16", "256", "1024", "4096", "16384")
    @JvmField
    var parallelism: Int = 0

    @Param("1", "256")
    @JvmField
    var tasksPerSlot: Int = 0

    @Param("0")
    @JvmField
    var complexity: Int = 0

    @Param("QUEUE", "JOX", "JOX_TRY")
    @JvmField
    var handoff: String = "QUEUE"

    fun ackerman(m: Int, n: Int): Int {
        if (m == 0) return n + 1
        if (n == 0) return ackerman(m - 1, 1)
        return ackerman(m - 1, ackerman(m, n - 1))
    }

    fun unitOfWork(): Int {
        return ackerman(3, complexity)
    }

    @Benchmark
    fun vtPerTask(): Int = Executors.newVirtualThreadPerTaskExecutor().use { threads ->
        runTasks(List(parallelism) { threads })
    }

    @Benchmark
    fun vtPerWorker(): Int {
        // One pending task at most; the second cell is reserved for the stop marker.
        val queues = List(parallelism) { newHandoff<Runnable>(2, singleLock = true) }
        val stop = Runnable {}
        return Executors.newVirtualThreadPerTaskExecutor().use { threads ->
            try {
                val workers = queues.map { queue ->
                    threads.submit {
                        while (true) {
                            val task = queue.receive()
                            if (task === stop) break
                            task.run()
                        }
                    }
                    Executor { task -> queue.send(task) }
                }
                runTasks(workers)
            } finally {
                queues.forEach { it.send(stop) }
            }
        }
    }

    private fun runTasks(executors: List<Executor>): Int {
        require(parallelism > 0 && tasksPerSlot > 0)
        val total = Math.multiplyExact(parallelism, tasksPerSlot)
        val completed = newHandoff<Pair<Int, Int>>(parallelism, singleLock = false)

        fun submit(slot: Int) {
            executors[slot].execute {
                completed.send(slot to unitOfWork())
            }
        }

        repeat(parallelism) { submit(it) }
        var remaining = total - parallelism
        var res = 0
        repeat(total) {
            val (slot, value) = completed.receive()
            res += value
            if (remaining > 0) {
                submit(slot)
                remaining--
            }
        }
        return res
    }

    private interface Handoff<T : Any> {
        fun send(value: T)
        fun receive(): T
    }

    private class QueueHandoff<T : Any>(private val queue: BlockingQueue<T>) : Handoff<T> {
        override fun send(value: T) { queue.add(value) }
        override fun receive(): T = queue.take()
    }

    private class JoxHandoff<T : Any>(capacity: Int, private val tryFirst: Boolean) : Handoff<T> {
        private val channel = Channel.newBufferedChannel<T>(capacity)

        override fun send(value: T) {
            // trySend can fail spuriously under contention: never drop a task/completion.
            if (!tryFirst || !channel.trySend(value)) channel.send(value)
        }

        override fun receive(): T =
            if (tryFirst) channel.tryReceive() ?: channel.receive() else channel.receive()
    }

    private fun <T : Any> newHandoff(capacity: Int, singleLock: Boolean): Handoff<T> = when (handoff) {
        "QUEUE" -> QueueHandoff(if (singleLock) ArrayBlockingQueue(capacity) else LinkedBlockingQueue())
        "JOX" -> JoxHandoff(capacity, tryFirst = false)
        "JOX_TRY" -> JoxHandoff(capacity, tryFirst = true)
        else -> error("Unknown handoff: $handoff")
    }
}
