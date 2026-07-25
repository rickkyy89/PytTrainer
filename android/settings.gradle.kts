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

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PytTrainer"
include(":app")
