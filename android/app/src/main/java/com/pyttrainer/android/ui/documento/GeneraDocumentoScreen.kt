package com.pyttrainer.android.ui.documento

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pyttrainer.android.R
import com.pyttrainer.android.auth.GestoreAccessoGoogle
import com.pyttrainer.android.dati.Esercizio
import com.pyttrainer.android.ui.comune.EventoUi

/**
 * Generazione del Google Doc (CLAUDE.md, "Flusso automatico completo"):
 * collega l'account Google (AppAuth), riepiloga quanti esercizi verranno
 * inseriti ed avvia PythonBridge.generaDocumento tramite
 * [GeneraDocumentoViewModel]. [gestoreAccessoGoogle] è condiviso con
 * SchedaScreen (stessa istanza, vive in SchedaViewModel): collegarsi da qui
 * aggiorna anche l'icona nuvola nella schermata principale.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GeneraDocumentoScreen(
    esercizi: List<Esercizio>,
    titolo: String,
    cartellaLavoro: String?,
    gestoreAccessoGoogle: GestoreAccessoGoogle,
    onIndietro: () -> Unit,
    onDocumentoGenerato: () -> Unit,
) {
    val testi = GeneraDocumentoTesti(
        nessunEsercizioPronto = stringResource(R.string.genera_documento_nessun_esercizio_pronto),
        erroreGenerico = stringResource(R.string.errore_sconosciuto),
        accessoCompletato = stringResource(R.string.genera_documento_accesso_completato),
        disconnesso = stringResource(R.string.genera_documento_disconnesso),
    )
    val viewModel: GeneraDocumentoViewModel = viewModel(
        factory = GeneraDocumentoViewModel.factory(esercizi, titolo, cartellaLavoro, gestoreAccessoGoogle, testi),
    )
    val stato by viewModel.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val contesto = LocalContext.current

    LaunchedEffect(viewModel) {
        viewModel.eventi.collect { evento ->
            when (evento) {
                is EventoUi.Errore -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.Info -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.EsercizioRimosso -> Unit // non emesso da questo schermo
            }
        }
    }

    val accessoLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { risultato -> risultato.data?.let(viewModel::completaAccesso) }

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
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Spacer(modifier = Modifier.height(4.dp))

            // --- Account Google -----------------------------------------------
            Text(stringResource(R.string.genera_documento_sezione_account), style = MaterialTheme.typography.titleMedium)
            if (!stato.configurato) {
                Text(
                    text = stringResource(R.string.genera_documento_non_configurato),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(
                        imageVector = if (stato.connesso) Icons.Default.CloudDone else Icons.Default.CloudOff,
                        contentDescription = null,
                        tint = if (stato.connesso) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                    )
                    Text(
                        text = if (stato.connesso) {
                            stringResource(R.string.genera_documento_connesso)
                        } else {
                            stringResource(R.string.genera_documento_non_connesso)
                        },
                    )
                }
                if (stato.connesso) {
                    OutlinedButton(onClick = viewModel::disconnetti, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.genera_documento_pulsante_disconnetti))
                    }
                } else {
                    Button(
                        onClick = { accessoLauncher.launch(viewModel.intentDiAccesso()) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.genera_documento_pulsante_collega))
                    }
                }
            }

            HorizontalDivider()

            // --- Riepilogo -------------------------------------------------------
            Text(stringResource(R.string.genera_documento_sezione_riepilogo), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.genera_documento_riepilogo_titolo, stato.titolo))
            Text(
                pluralStringResource(
                    R.plurals.genera_documento_riepilogo_conteggio,
                    // La forma singolare/plurale segue il NUMERO DI PRONTI (il
                    // soggetto della frase), non il totale: "1 esercizio pronto
                    // su 3 verrà inserito".
                    stato.eserciziPronti,
                    stato.eserciziPronti,
                    stato.eserciziTotali,
                )
            )
            if (stato.eserciziEsclusi > 0) {
                Text(
                    text = pluralStringResource(
                        R.plurals.genera_documento_esercizi_esclusi,
                        stato.eserciziEsclusi,
                        stato.eserciziEsclusi,
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (stato.statoRipresa != null) {
                Text(
                    text = stringResource(R.string.genera_documento_ripresa_avviso),
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            HorizontalDivider()

            // --- Generazione -------------------------------------------------------
            Button(
                onClick = { viewModel.genera(onDocumentoGenerato) },
                enabled = stato.generabile,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.genera_documento_pulsante_genera))
            }
            if (stato.generazioneInCorso) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    Text(
                        text = stringResource(R.string.genera_documento_generazione_in_corso),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }

            stato.risultato?.let { risultato ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(stringResource(R.string.genera_documento_risultato_titolo), fontWeight = FontWeight.Medium)
                        OutlinedButton(
                            onClick = { contesto.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(risultato.url))) },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Default.OpenInBrowser, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(stringResource(R.string.genera_documento_pulsante_apri))
                        }
                        if (risultato.eserciziInseriti.isNotEmpty()) {
                            Text(
                                text = stringResource(R.string.genera_documento_esercizi_inseriti_titolo),
                                style = MaterialTheme.typography.labelLarge,
                            )
                            risultato.eserciziInseriti.forEach { nome ->
                                Text(text = "• $nome", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}
