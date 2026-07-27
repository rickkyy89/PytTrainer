// Build file di root: dichiara soltanto i plugin (via "apply false"), che
// vengono poi effettivamente applicati nei moduli che li usano (qui solo
// ":app"). Non contiene configurazioni di dipendenze: quelle vivono in
// app/build.gradle.kts.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.chaquopy) apply false
}
