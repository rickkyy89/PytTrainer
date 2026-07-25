package com.pyttrainer.android.ui.scheda

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.R
import com.pyttrainer.android.dati.Esercizio

/**
 * Dialog di inserimento manuale (Fase 3): equivalente del form
 * "Inserimento manuale" di app.py. Il nome è l'unico campo obbligatorio.
 */
@Composable
fun InserisciEsercizioDialog(
    onConferma: (Esercizio) -> Unit,
    onAnnulla: () -> Unit,
) {
    var nome by remember { mutableStateOf("") }
    var spiegazione by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var ripetizioni by remember { mutableStateOf("") }
    var recupero by remember { mutableStateOf("") }
    var gruppo by remember { mutableStateOf("") }
    var erroreNome by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onAnnulla,
        title = { Text(stringResource(R.string.aggiungi_esercizio_titolo)) },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = nome,
                    onValueChange = { nome = it; erroreNome = false },
                    label = { Text(stringResource(R.string.campo_nome)) },
                    isError = erroreNome,
                    supportingText = {
                        if (erroreNome) Text(stringResource(R.string.campo_nome_obbligatorio))
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = spiegazione,
                    onValueChange = { spiegazione = it },
                    label = { Text(stringResource(R.string.campo_spiegazione)) },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    label = { Text(stringResource(R.string.campo_note)) },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = ripetizioni,
                    onValueChange = { ripetizioni = it },
                    label = { Text(stringResource(R.string.campo_ripetizioni)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = recupero,
                    onValueChange = { recupero = it },
                    label = { Text(stringResource(R.string.campo_recupero)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = gruppo,
                    onValueChange = { gruppo = it },
                    label = { Text(stringResource(R.string.campo_gruppo)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (nome.isBlank()) {
                    erroreNome = true
                } else {
                    onConferma(
                        Esercizio(
                            nome = nome.trim(),
                            spiegazione = spiegazione,
                            note = note,
                            ripetizioni = ripetizioni,
                            recupero = recupero,
                            gruppo = gruppo.trim(),
                        )
                    )
                }
            }) {
                Text(stringResource(R.string.azione_conferma))
            }
        },
        dismissButton = {
            TextButton(onClick = onAnnulla) {
                Text(stringResource(R.string.azione_annulla))
            }
        },
    )
}
