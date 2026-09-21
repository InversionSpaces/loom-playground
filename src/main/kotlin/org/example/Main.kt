package org.example

import java.util.concurrent.Executors
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext

fun main() {
    Executors.newVirtualThreadPerTaskExecutor().asCoroutineDispatcher().use { dispatcher ->
        runBlocking {
            withContext(dispatcher) {
                check(Thread.currentThread().isVirtual)
                println("Kotlin coroutine running on a JDK ${Runtime.version().feature()} virtual thread")
            }
        }
    }
}
