package com.pyttrainer.android.ui.scheda

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.R
import com.pyttrainer.android.ui.comune.EventoUi

/**
 * Schermata principale (Fase 3): copre quel che nell'app Streamlit sta nella
 * sidebar (titolo, file scheda, credenziali Google, svuota lista) e nella
 * lista esercizi con expander.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SchedaScreen(
    viewModel: SchedaViewModel,
    onEsercizioClick: (String) -> Unit,
    onGeneraDocumentoClick: () -> Unit,
    onImpostazioniClick: () -> Unit,
) {
    val stato by viewModel.stato.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    var menuAperto by remember { mutableStateOf(false) }
    var dialogAggiungiAperto by remember { mutableStateOf(false) }
    var dialogSvuotaAperto by remember { mutableStateOf(false) }

    val etichettaAnnulla = stringResource(R.string.scheda_esercizio_rimosso_azione)
    val modelloEsercizioRimosso = stringResource(R.string.scheda_esercizio_rimosso_messaggio)

    LaunchedEffect(viewModel) {
        viewModel.eventi.collect { evento ->
            when (evento) {
                is EventoUi.Errore -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.Info -> snackbarHostState.showSnackbar(evento.messaggio)
                is EventoUi.EsercizioRimosso -> {
                    val risultato = snackbarHostState.showSnackbar(
                        message = modelloEsercizioRimosso.format(evento.nomeEsercizio),
                        actionLabel = etichettaAnnulla,
                        duration = SnackbarDuration.Short,
                    )
                    if (risultato == SnackbarResult.ActionPerformed) viewModel.ripristinaUltimoRimosso()
                }
            }
        }
    }

    val nomeFileSuggerito = stato.titolo.trim().ifBlank { "scheda" }
        .replace(Regex("[\\\\/:*?\"<>|]"), "_")

    val apriSchedaLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let(viewModel::apriScheda)
    }
    val salvaComeLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/zip")
    ) { uri -> uri?.let(viewModel::salvaCome) }
    val importaCsvLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let(viewModel::importaCsvAnteprima)
    }
    val esportaCsvLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri -> uri?.let(viewModel::esportaCsv) }

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text(stringResource(R.string.app_name)) },
                    actions = {
                        IconButton(onClick = { menuAperto = true }) {
                            Icon(
                                imageVector = Icons.Default.MoreVert,
                                contentDescription = stringResource(R.string.scheda_menu_content_description),
                            )
                        }
                        DropdownMenu(expanded = menuAperto, onDismissRequest = { menuAperto = false }) {
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_apri)) },
                                onClick = {
                                    menuAperto = false
                                    apriSchedaLauncher.launch(arrayOf("*/*"))
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_salva)) },
                                enabled = stato.bundleApribile,
                                onClick = {
                                    menuAperto = false
                                    viewModel.salva()
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_salva_come)) },
                                onClick = {
                                    menuAperto = false
                                    salvaComeLauncher.launch("$nomeFileSuggerito.scheda")
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_importa_csv)) },
                                onClick = {
                                    menuAperto = false
                                    importaCsvLauncher.launch(arrayOf("*/*"))
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_esporta_csv)) },
                                onClick = {
                                    menuAperto = false
                                    esportaCsvLauncher.launch("$nomeFileSuggerito.csv")
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_svuota)) },
                                onClick = {
                                    menuAperto = false
                                    dialogSvuotaAperto = true
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.scheda_menu_impostazioni)) },
                                onClick = {
                                    menuAperto = false
                                    onImpostazioniClick()
                                },
                            )
                        }
                    },
                )
                if (stato.caricamento) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
            }
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { dialogAggiungiAperto = true }) {
                Icon(Icons.Default.Add, contentDescription = stringResource(R.string.scheda_fab_aggiungi_desc))
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
        ) {
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = stato.titolo,
                onValueChange = viewModel::impostaTitolo,
                label = { Text(stringResource(R.string.scheda_titolo_label)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(modifier = Modifier.height(8.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.clickable(onClick = onImpostazioniClick),
            ) {
                Icon(
                    imageVector = if (stato.statoGoogleConnesso) Icons.Default.CloudDone else Icons.Default.CloudOff,
                    contentDescription = null,
                    tint = if (stato.statoGoogleConnesso) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.outline
                    },
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = if (stato.statoGoogleConnesso) {
                        stringResource(R.string.scheda_google_connesso)
                    } else {
                        stringResource(R.string.scheda_google_non_connesso)
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Text(
                text = stato.nomeFileVisualizzato?.let { stringResource(R.string.scheda_nome_file_label, it) }
                    ?: stringResource(R.string.scheda_nome_file_nessuno),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.scheda_contatore_pronti, stato.eserciziPronti, stato.esercizi.size),
                style = MaterialTheme.typography.titleSmall,
            )
            Spacer(modifier = Modifier.height(4.dp))

            if (stato.esercizi.isEmpty()) {
                Box(modifier = Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text(
                        text = stringResource(R.string.scheda_lista_vuota),
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                ListaEserciziRiordinabile(
                    esercizi = stato.esercizi,
                    onEsercizioClick = onEsercizioClick,
                    onRiordina = viewModel::riordina,
                    onRimuovi = viewModel::rimuoviEsercizio,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                )
            }

            Button(
                onClick = onGeneraDocumentoClick,
                enabled = stato.eserciziPronti > 0,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp),
            ) {
                Text(stringResource(R.string.scheda_pulsante_genera_documento))
            }
        }
    }

    if (dialogAggiungiAperto) {
        InserisciEsercizioDialog(
            onConferma = { esercizio ->
                viewModel.aggiungiEsercizio(esercizio)
                dialogAggiungiAperto = false
            },
            onAnnulla = { dialogAggiungiAperto = false },
        )
    }

    if (dialogSvuotaAperto) {
        AlertDialog(
            onDismissRequest = { dialogSvuotaAperto = false },
            title = { Text(stringResource(R.string.scheda_svuota_conferma_titolo)) },
            text = { Text(stringResource(R.string.scheda_svuota_conferma_testo)) },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.svuotaLista()
                    dialogSvuotaAperto = false
                }) { Text(stringResource(R.string.azione_conferma)) }
            },
            dismissButton = {
                TextButton(onClick = { dialogSvuotaAperto = false }) {
                    Text(stringResource(R.string.azione_annulla))
                }
            },
        )
    }

    stato.anteprimaImportCsv?.let { anteprima ->
        ImportaCsvAnteprimaDialog(
            esercizi = anteprima,
            onConferma = { viewModel.confermaImportCsv() },
            onAnnulla = { viewModel.annullaImportCsv() },
        )
    }
}
