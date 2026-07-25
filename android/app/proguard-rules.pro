# Regole ProGuard/R8 del modulo app. Il build di release attuale ha
# isMinifyEnabled = false (nessuna offuscazione/shrink in questa fase), ma il
# file resta pronto per quando verrà abilitato.

# Chaquopy gestisce da sé le regole necessarie al proprio runtime tramite il
# consumer-rules incluso nell'artefatto del plugin: non serve aggiungerne qui.

# kotlinx.serialization: mantenere i serializer generati dei @Serializable
# data class del pacchetto dati (servirà quando isMinifyEnabled tornerà true).
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class com.pyttrainer.android.** {
    *** Companion;
}
-keepclasseswithmembers class com.pyttrainer.android.** {
    kotlinx.serialization.KSerializer serializer(...);
}
