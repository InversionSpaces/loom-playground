plugins {
    kotlin("jvm") version "2.4.10"
    application
    id("me.champeau.jmh") version "0.7.3"
}

group = "org.example"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.11.0")
    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin {
    jvmToolchain(26)
}

application {
    mainClass.set("org.example.MainKt")
}

tasks.test {
    useJUnitPlatform()
}

val jmhSmoke = providers.gradleProperty("jmhSmoke").map(String::toBoolean).orElse(false)

jmh {
    jmhVersion.set("1.37")
    includeTests.set(false)
    failOnError.set(true)
    warmupIterations.set(jmhSmoke.map { if (it) 1 else 3 })
    iterations.set(jmhSmoke.map { if (it) 1 else 5 })
    fork.set(jmhSmoke.map { if (it) 1 else 2 })
    warmup.set(jmhSmoke.map { if (it) "100ms" else "1s" })
    timeOnIteration.set(jmhSmoke.map { if (it) "100ms" else "1s" })
    resultFormat.set("JSON")
    resultsFile.set(layout.buildDirectory.file("reports/jmh/results.json"))
    includes.set(listOf(providers.gradleProperty("benchmark").getOrElse(".*")))
}
