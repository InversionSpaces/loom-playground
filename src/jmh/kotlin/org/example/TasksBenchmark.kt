package org.example

import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.Executor
import java.util.concurrent.ExecutorCompletionService
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import org.openjdk.jmh.annotations.Benchmark
import org.openjdk.jmh.annotations.BenchmarkMode
import org.openjdk.jmh.annotations.Mode
import org.openjdk.jmh.annotations.OutputTimeUnit
import org.openjdk.jmh.annotations.Param
import org.openjdk.jmh.annotations.Scope
import org.openjdk.jmh.annotations.State

@State(Scope.Benchmark)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
open class TasksBenchmark {
    @Param("1", "4", "16", "64", "256", "1024")
    @JvmField
    var parallelism: Int = 0

    @Param("1", "16", "256", "4096")
    @JvmField
    var tasksPerSlot: Int = 0

    @Param("0")
    @JvmField
    var complexity: Int = 0

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
        val queues = List(parallelism) { ArrayBlockingQueue<Runnable>(2) }
        val stop = Runnable {}
        return Executors.newVirtualThreadPerTaskExecutor().use { threads ->
            try {
                val workers = queues.map { queue ->
                    threads.submit {
                        while (true) {
                            val task = queue.take()
                            if (task === stop) break
                            task.run()
                        }
                    }
                    Executor { task -> queue.add(task) }
                }
                runTasks(workers)
            } finally {
                queues.forEach { it.add(stop) }
            }
        }
    }

    private fun runTasks(executors: List<Executor>): Int {
        require(parallelism > 0 && tasksPerSlot > 0)
        val total = Math.multiplyExact(parallelism, tasksPerSlot)
        val completed = LinkedBlockingQueue<Future<Pair<Int, Int>>>()
        val slots = executors.map { ExecutorCompletionService(it, completed) }

        fun submit(slot: Int) {
            slots[slot].submit { slot to unitOfWork() }
        }

        repeat(parallelism) { submit(it) }
        var remaining = total - parallelism
        var res = 0
        repeat(total) {
            val (slot, value) = completed.take().get()
            res += value
            if (remaining > 0) {
                submit(slot)
                remaining--
            }
        }
        return res
    }
}
