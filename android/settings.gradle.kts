// Configurazione dei repository Gradle: pluginManagement per i plugin (AGP,
// Kotlin, Chaquopy, ...), dependencyResolutionManagement per le dipendenze
// delle librerie (AndroidX, Compose, AppAuth, ...). Chaquopy 17.0.0 è
// pubblicato su Maven Central, quindi non serve un repository Maven
// dedicato (a differenza delle versioni più vecchie del plugin, che
// richiedevano https://chaquo.com/maven).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

// Auto-provisioning delle toolchain Java: il progetto compila con JDK 17
// (vedi jvmToolchain(17) in app/build.gradle.kts), ma sulle macchine di
// sviluppo spesso c'è solo il JBR di Android Studio (JDK 21). Con questo
// plugin Gradle scarica da solo il JDK 17 mancante invece di fallire, così
// non serve installarlo a mano e la build resta identica a quella della CI.
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "0.10.0"
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PytTrainer"
include(":app")
