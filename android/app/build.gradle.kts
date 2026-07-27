// Modulo applicazione: qui vive sia la configurazione Android/Kotlin/Compose
// standard sia il blocco Chaquopy che imbarca l'interprete Python 3.11 e i 4
// moduli condivisi della radice del repo (video_helper, scheda_file,
// csv_utils, google_docs_helper) + android_bridge.py (unico file Python
// specifico di questo modulo).

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.chaquopy)
}

// Versione major.minor di Python richiesta da Chaquopy, definita una sola
// volta in gradle.properties (deve corrispondere alla versione di Python
// installata sulla macchina che esegue la build: Chaquopy la usa per il pip
// install delle dipendenze in fase di build).
val versionePython: String = providers.gradleProperty("pyttrainer.python.version").get()

// Client ID OAuth "Android" (Google Cloud Console), vedi il commento in
// gradle.properties per come crearlo. Vuoto finché non è stato creato: in tal
// caso GestoreAccessoGoogle.configurato() torna false e la UI lo spiega
// invece di aprire un login destinato a fallire.
val clientIdOAuth: String =
    providers.gradleProperty("pyttrainer.oauth.clientId").getOrElse("")

// Schema dell'URI di redirect OAuth registrato da AppAuth nel manifest (la
// libreria dichiara la propria RedirectUriReceiverActivity con il placeholder
// ${appAuthRedirectScheme}: senza un valore il manifest merger fallisce).
//
// DERIVATO dal client ID invece di essere configurato separatamente: un
// client ID Android "123-abc.apps.googleusercontent.com" corrisponde SEMPRE
// allo schema invertito "com.googleusercontent.apps.123-abc" (è una
// convenzione fissa di Google, non un'euristica). Tenere le due proprietà
// indipendenti è una fonte classica di disallineamento silenzioso: si
// aggiorna il client ID e ci si scorda dello schema, il login fallisce con
// redirect_uri_mismatch e il messaggio di Google non lascia capire perché.
val schemaRedirectOAuth: String = if (clientIdOAuth.isNotBlank()) {
    "com.googleusercontent.apps.${clientIdOAuth.substringBefore(".apps.googleusercontent.com")}"
} else {
    // Nessun client ancora configurato: resta il segnaposto storico (vedi
    // gradle.properties), che permette comunque di compilare.
    providers.gradleProperty("pyttrainer.oauth.redirectScheme").get()
}

// URI di redirect completo per AuthorizationRequest (AppAuth vuole l'URI
// intero, non solo lo schema): il path "/oauth2redirect" è arbitrario ma
// deve combaciare tra qui e la configurazione del client su Google Cloud
// Console solo per lo SCHEMA (Google non valida il path per i client
// "Android", solo lo schema custom).
val redirectUriOAuth: String = "$schemaRedirectOAuth:/oauth2redirect"

android {
    namespace = "com.pyttrainer.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.pyttrainer.android"
        minSdk = 26 // Chaquopy 17 richiede minSdk >= 24; 26 dà accesso a java.time senza desugaring extra.
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Consumato dal manifest di AppAuth (net.openid:appauth): è lo schema
        // dell'URI su cui Google rimanda il browser a fine login.
        manifestPlaceholders["appAuthRedirectScheme"] = schemaRedirectOAuth

        // Esposti a runtime per GestoreAccessoGoogle: niente file di
        // configurazione separato da leggere/parsare, il valore Gradle
        // diventa direttamente una costante Kotlin generata.
        buildConfigField("String", "OAUTH_CLIENT_ID", "\"$clientIdOAuth\"")
        buildConfigField("String", "OAUTH_REDIRECT_URI", "\"$redirectUriOAuth\"")

        // Python 3.11 supporta ancora le ABI a 32 bit, ma le omettiamo: nessun
        // device recente le richiede e ogni ABI in più appesantisce l'APK con
        // una copia separata del runtime Python imbarcato da Chaquopy.
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    // Keystore di debug condiviso (committato in android/keystore/debug.keystore):
    // così build locali e CI producono la stessa impronta SHA-1, necessaria per
    // registrare un'unica origine OAuth su Google Cloud Console.
    signingConfigs {
        getByName("debug") {
            storeFile = rootProject.file("keystore/debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // In questa fase non firmiamo il build di release con una chiave
            // dedicata (arriverà con la pubblicazione): resta non firmato.
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true // per OAUTH_CLIENT_ID/OAUTH_REDIRECT_URI in BuildConfig.
    }

    // yt-dlp, google-api-python-client e Chaquopy stesso imbarcano più file
    // META-INF/LICENSE, NOTICE, DEPENDENCIES ecc. con lo stesso percorso: senza
    // queste esclusioni il merge delle risorse fallisce con un conflitto.
    packaging {
        resources {
            excludes += setOf(
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE",
                "META-INF/LICENSE.txt",
                "META-INF/LICENSE.md",
                "META-INF/NOTICE",
                "META-INF/NOTICE.txt",
                "META-INF/NOTICE.md",
                "META-INF/INDEX.LIST",
            )
        }
    }
}

// Toolchain JDK 17 per la compilazione Kotlin (coerente con compileOptions
// sopra e con setup-java@v4 Temurin 17 nel workflow CI).
kotlin {
    jvmToolchain(17)
}

// --- Copia dei moduli Python condivisi (niente duplicazione in git) -------
//
// I 4 moduli Python (video_helper.py, scheda_file.py, csv_utils.py,
// google_docs_helper.py) restano SOLO nella radice del repo, così il codice
// eseguito su desktop (Streamlit) e su Android è letteralmente lo stesso
// file. Questo task Sync li copia (senza modificarli) nella cartella di
// build, da cui Chaquopy li include come sourceSet Python aggiuntivo.
//
// Nota sui percorsi: la root del progetto Gradle è "android/", quindi la
// radice del repo (dove vivono i moduli condivisi) è la cartella PADRE del
// progetto radice Gradle, cioè rootProject.projectDir.parentFile.
val moduliPythonCondivisi = listOf(
    "video_helper.py",
    "scheda_file.py",
    "csv_utils.py",
    "google_docs_helper.py",
)
val cartellaModuliCondivisiGenerata = layout.buildDirectory.dir("generated/python")

val copiaModuliPython by tasks.registering(Sync::class) {
    description = "Copia i moduli Python condivisi dalla radice del repo nella build Android."
    from(rootProject.projectDir.parentFile) {
        include(moduliPythonCondivisi)
    }
    into(cartellaModuliCondivisiGenerata)
}

// Qualunque task il cui nome contenga "Python" (quelli generati dal plugin
// Chaquopy: extractPython..., pipInstall..., ecc.) deve prima trovare i
// moduli condivisi già copiati nella cartella generata.
//
// L'esclusione di copiaModuliPython stesso NON è cosmetica: anche il suo nome
// contiene "Python", quindi senza il filtro il task dipenderebbe da sé stesso
// e Gradle fallirebbe subito con "Circular dependency between the following
// tasks: :app:copiaModuliPython".
tasks.matching { it.name.contains("Python") && it.name != copiaModuliPython.name }.configureEach {
    dependsOn(copiaModuliPython)
}

chaquopy {
    defaultConfig {
        // Deve corrispondere esattamente alla versione dell'interprete Python
        // installato sulla macchina di build (vedi gradle.properties).
        version = versionePython

        pip {
            // Stesso set di dipendenze runtime di requirements.txt, MENO
            // streamlit (qui l'interfaccia è nativa).
            //
            // Versioni fissate per una build riproducibile: yt-dlp pubblica
            // release molto frequenti, quindi la pin va aggiornata di tanto
            // in tanto (yt-dlp smette di funzionare quando YouTube cambia il
            // proprio player interno).
            // Aggiornata il 2026-07-25: con la 2025.06.30 YouTube rispondeva
            // "The following content is not available on this app" a ogni
            // estrazione di informazioni (la ricerca invece funzionava
            // ancora), rendendo impossibile estrarre i frame.
            install("yt-dlp==2026.7.4")
            install("google-api-python-client==2.149.0")
            install("google-auth==2.35.0")
            install("google-auth-httplib2==0.2.0")
            // google-auth-oauthlib serve anche se l'OAuth lo gestisce Kotlin:
            // google_docs_helper importa InstalledAppFlow a livello di modulo.
            install("google-auth-oauthlib==1.2.1")
            // Pillow serve al ritaglio dei frame: riusando video_helper.crop_frame()
            // il risultato è identico a quello del desktop (stessa matematica,
            // stessa qualità JPEG), invece di riscrivere il ritaglio in Kotlin e
            // rischiare immagini diverse tra PC e telefono. È un pacchetto
            // nativo: Chaquopy lo prende dal proprio repository di wheel
            // precompilate, quindi va lasciato SENZA versione fissata (una pin
            // che quel repository non ha farebbe fallire la build).
            install("Pillow")
        }
    }

    sourceSets {
        getByName("main") {
            // src/main/python (default) ospita android_bridge.py; qui
            // aggiungiamo la cartella generata dal task copiaModuliPython.
            srcDir(cartellaModuliCondivisiGenerata)
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    debugImplementation(libs.androidx.compose.ui.tooling)

    implementation(libs.androidx.navigation.compose)

    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)

    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.security.crypto)

    implementation(libs.coil.compose)

    implementation(libs.kotlinx.serialization.json)

    implementation(libs.appauth)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
