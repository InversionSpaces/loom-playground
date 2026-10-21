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
    add("jmhImplementation", "com.softwaremill.jox:channels:1.1.2")
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
    if (jmhSmoke.get()) {
        fork.set(1)
        warmupIterations.set(1)
        iterations.set(1)
        warmup.set("100ms")
        timeOnIteration.set("100ms")
    }
    resultFormat.set("JSON")
    resultsFile.set(layout.buildDirectory.file("reports/jmh/results.json"))
    includes.set(listOf(providers.gradleProperty("benchmark").getOrElse(".*")))
}
