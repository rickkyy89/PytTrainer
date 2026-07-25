package com.pyttrainer.android.ui.documento

import android.Manifest
import android.app.Application
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pyttrainer.android.R
import com.pyttrainer.android.dati.Esercizio

/**
 * Generazione del Google Doc (Fase 7): invia solo gli esercizi pronti (come
 * app.py) a GenerazioneDocumentoWorker (CoroutineWorker in primo piano,
 * notifica di avanzamento) e ne osserva il progresso tramite
 * GeneraDocumentoViewModel/WorkManager. Se Google non è connesso mostra
 * l'invito ad andare in Impostazioni invece di abilitare il pulsante.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GeneraDocumentoScreen(
    esercizi: List<Esercizio>,
    titolo: String,
    cartellaLavoro: String?,
    onIndietro: () -> Unit,
    onImpostazioniClick: () -> Unit,
    onGenerazioneCompletata: () -> Unit,
) {
    val eserciziPronti = remember(esercizi) { esercizi.filter { it.pronto } }
    val testi = GeneraDocumentoTesti(
        nessunEsercizioPronto = stringResource(R.string.genera_documento_nessun_esercizio_pronto),
        googleNonConnesso = stringResource(R.string.genera_documento_google_non_connesso),
        erroreGenerico = stringResource(R.string.errore_sconosciuto),
    )
    val contesto = LocalContext.current
    val viewModel: GeneraDocumentoViewModel = viewModel(
        factory = GeneraDocumentoViewModel.factory(
            contesto.applicationContext as Application, eserciziPronti, titolo, cartellaLavoro, testi,
        ),
    )
    val stato by viewModel.stato.collectAsState()
    val gestoreUri = LocalUriHandler.current

    LaunchedEffect(stato.url) {
        if (stato.url != null) onGenerazioneCompletata()
    }

    // Android 13+: la notifica di avanzamento richiede il permesso a runtime.
    // Un rifiuto non è bloccante: il worker gira comunque, semplicemente
    // senza notifica visibile.
    val lanciatorePermessoNotifiche = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { viewModel.avviaGenerazione() }

    fun avviaConPermesso() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            lanciatorePermessoNotifiche.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            viewModel.avviaGenerazione()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.genera_documento_titolo)) },
                navigationIcon = {
                    IconButton(onClick = onIndietro) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.azione_indietro))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = stringResource(R.string.genera_documento_contatore, eserciziPronti.size, esercizi.size),
                style = MaterialTheme.typography.titleMedium,
            )

            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = if (stato.statoGoogleConnesso) Icons.Default.CloudDone else Icons.Default.CloudOff,
                    contentDescription = null,
                    tint = if (stato.statoGoogleConnesso) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = if (stato.statoGoogleConnesso) {
                        stringResource(R.string.scheda_google_connesso)
                    } else {
                        stringResource(R.string.scheda_google_non_connesso)
                    },
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            if (!stato.statoGoogleConnesso) {
                OutlinedButton(onClick = onImpostazioniClick, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.genera_documento_vai_a_impostazioni))
                }
            }

            if (stato.generazioneAvviata) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    LinearProgressIndicator(
                        progress = { if (stato.totale > 0) stato.fatti.toFloat() / stato.totale else 0f },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        text = stringResource(R.string.genera_documento_avanzamento, stato.fatti, stato.totale),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            stato.errore?.let { messaggioErrore ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = messaggioErrore,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }

            stato.url?.let { url ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(stringResource(R.string.genera_documento_completata))
                        OutlinedButton(onClick = { gestoreUri.openUri(url) }, modifier = Modifier.fillMaxWidth()) {
                            Icon(Icons.Default.OpenInNew, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(stringResource(R.string.genera_documento_apri_documento))
                        }
                    }
                }
            }

            Button(
                onClick = ::avviaConPermesso,
                enabled = !stato.generazioneAvviata && eserciziPronti.isNotEmpty() && stato.statoGoogleConnesso,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.scheda_pulsante_genera_documento))
            }
        }
    }
}
