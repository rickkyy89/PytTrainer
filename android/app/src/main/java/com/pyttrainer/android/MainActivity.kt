package com.pyttrainer.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.python.EsitoAvvio
import com.pyttrainer.android.python.PythonBridge
import com.pyttrainer.android.ui.theme.PytTrainerTheme
import kotlinx.coroutines.launch

/**
 * Activity unica di questa fase: ospita solo la schermata di verifica del
 * cablaggio Chaquopy (versione Python, esito registrazione del backend nativo
 * di estrazione frame, ricerca YouTube di prova). Le schermate vere
 * (creazione/apertura scheda, scelta video, generazione documento, ...)
 * arrivano nelle fasi successive.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PytTrainerTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    SchermataVerificaCablaggio()
                }
            }
        }
    }
}

@Composable
private fun SchermataVerificaCablaggio() {
    var versionePython by remember { mutableStateOf("in caricamento…") }
    var ricercaInCorso by remember { mutableStateOf(false) }
    var risultatoRicercaGrezzo by remember { mutableStateOf<String?>(null) }
    val ambitoCoroutine = rememberCoroutineScope()
    val nomeEsercizioProva = stringResource(R.string.verifica_ricerca_esercizio_prova)

    // Eseguita una sola volta all'ingresso nella schermata: dimostra che una
    // chiamata Python "semplice" (nessun argomento) funziona subito, senza
    // interazione dell'utente.
    LaunchedEffect(Unit) {
        versionePython = PythonBridge.versionePython()
            .getOrElse { errore -> "Errore: ${errore.message}" }
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.verifica_titolo),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )

            HorizontalDivider()

            Text(
                text = stringResource(R.string.verifica_versione_python_label),
                style = MaterialTheme.typography.labelLarge,
            )
            Text(text = versionePython, style = MaterialTheme.typography.bodyMedium)

            HorizontalDivider()

            Text(
                text = stringResource(R.string.verifica_backend_frame_label),
                style = MaterialTheme.typography.labelLarge,
            )
            Text(text = EsitoAvvio.rispostaRegistrazioneBackend, style = MaterialTheme.typography.bodyMedium)

            HorizontalDivider()

            Button(
                onClick = {
                    ricercaInCorso = true
                    risultatoRicercaGrezzo = null
                    ambitoCoroutine.launch {
                        risultatoRicercaGrezzo = PythonBridge.chiamaGrezza(
                            "cerca_video",
                            nomeEsercizioProva,
                            3,
                        )
                        ricercaInCorso = false
                    }
                },
                enabled = !ricercaInCorso,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(text = stringResource(R.string.verifica_pulsante_ricerca))
            }

            if (ricercaInCorso) {
                Text(text = stringResource(R.string.verifica_ricerca_in_corso))
                CircularProgressIndicator()
            }

            risultatoRicercaGrezzo?.let { grezzo ->
                Text(
                    text = stringResource(R.string.verifica_json_grezzo_label),
                    style = MaterialTheme.typography.labelLarge,
                )
                Text(text = grezzo, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
