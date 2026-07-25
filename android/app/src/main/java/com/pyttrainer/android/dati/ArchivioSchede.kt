package com.pyttrainer.android.dati

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.io.IOException
import java.util.zip.CRC32
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Incapsula la danza tra Storage Access Framework (Uri content://, gestiti
 * dal sistema/altre app: Drive, file manager, email, ...) e i percorsi di
 * file reali su cui lavora Python via [com.pyttrainer.android.python.PythonBridge].
 *
 * Python non sa cosa sia un Uri content://: ogni operazione (carica_scheda,
 * importa_csv, ...) vuole un percorso di file reale. Questa classe copia il
 * contenuto di un Uri in un file nella cache privata dell'app
 * (`context.filesDir`), lo restituisce per l'uso lato Python, e permette poi
 * di riscrivere il file locale aggiornato sull'Uri di destinazione.
 *
 * Il percorso locale associato a un Uri è deterministico (derivato da un
 * hash dell'Uri stesso), così più operazioni sullo stesso file (es. "Salva"
 * ripetuto) riusano lo stesso file locale invece di accumularne di nuovi.
 */
class ArchivioSchede(private val contesto: Context) {

    /** Cartella dentro filesDir che ospita le copie locali di file aperti/salvati via SAF. */
    private val cartellaCache: File
        get() = File(contesto.filesDir, "schede_saf").apply { mkdirs() }

    /**
     * Percorso locale deterministico per [uri]: stesso Uri -> stesso file,
     * così "Salva" dopo "Apri" scrive/legge sempre lo stesso file di cache.
     * Non copia nulla, calcola solo il percorso.
     */
    fun percorsoLocalePer(uri: Uri): File {
        val crc = CRC32().apply { update(uri.toString().toByteArray(Charsets.UTF_8)) }
        val hash = crc.value.toString(16)
        val nomeOriginale = nomeVisualizzato(uri)?.let(::sanitizzaNomeFile) ?: "file"
        return File(cartellaCache, "${hash}_$nomeOriginale")
    }

    /**
     * Copia il contenuto di [uri] nel file locale determinato da
     * [percorsoLocalePer] e restituisce quel file, pronto per essere passato
     * a PythonBridge. Persiste anche il permesso di lettura sull'Uri.
     */
    suspend fun copiaDaUri(uri: Uri): File = withContext(Dispatchers.IO) {
        persistiPermesso(uri, scrittura = false)
        val destinazione = percorsoLocalePer(uri)
        val input = contesto.contentResolver.openInputStream(uri)
            ?: throw IOException("Impossibile aprire il file selezionato (Uri non risolvibile): $uri")
        input.use { flussoIngresso ->
            destinazione.outputStream().use { flussoUscita -> flussoIngresso.copyTo(flussoUscita) }
        }
        destinazione
    }

    /**
     * Riscrive il contenuto di [fileLocale] sull'Uri di destinazione
     * (troncando quanto già presente: "wt", come da contratto di
     * ContentResolver.openOutputStream). Persiste anche il permesso di
     * scrittura, così un successivo "Salva" sullo stesso Uri funziona anche
     * dopo un riavvio dell'app.
     */
    suspend fun copiaSuUri(fileLocale: File, uri: Uri) = withContext(Dispatchers.IO) {
        persistiPermesso(uri, scrittura = true)
        val output = contesto.contentResolver.openOutputStream(uri, "wt")
            ?: throw IOException("Impossibile scrivere sul file di destinazione (Uri non risolvibile): $uri")
        output.use { flussoUscita ->
            fileLocale.inputStream().use { flussoIngresso -> flussoIngresso.copyTo(flussoUscita) }
        }
    }

    /**
     * Persiste il permesso su [uri] oltre la vita del processo corrente
     * (necessario perché "Salva" continui a funzionare dopo un riavvio
     * dell'app, non solo nella sessione in cui l'Uri è stato scelto).
     * Un fallimento qui (es. Uri che non supporta permessi persistibili,
     * come alcuni provider FileProvider di terze parti) non è fatale: viene
     * ignorato, l'operazione di lettura/scrittura corrente prosegue comunque
     * grazie al permesso "una tantum" concesso dal picker.
     */
    fun persistiPermesso(uri: Uri, scrittura: Boolean) {
        val flag = if (scrittura) {
            Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        } else {
            Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        try {
            contesto.contentResolver.takePersistableUriPermission(uri, flag)
        } catch (_: SecurityException) {
            // Vedi commento sopra: non fatale.
        }
    }

    /** Nome da mostrare all'utente (colonna DISPLAY_NAME del content provider), o null se non disponibile. */
    fun nomeVisualizzato(uri: Uri): String? {
        if (uri.scheme != "content") return uri.lastPathSegment
        val cursore = contesto.contentResolver.query(uri, null, null, null, null) ?: return null
        cursore.use {
            val indiceNome = it.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (indiceNome < 0 || !it.moveToFirst()) return null
            return it.getString(indiceNome)
        }
    }

    private fun sanitizzaNomeFile(nome: String): String =
        nome.replace(Regex("[^A-Za-z0-9._-]"), "_").take(60).ifBlank { "file" }
}
