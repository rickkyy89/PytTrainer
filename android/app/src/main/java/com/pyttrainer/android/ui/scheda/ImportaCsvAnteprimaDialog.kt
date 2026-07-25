package com.pyttrainer.android.ui.scheda

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.pyttrainer.android.R
import com.pyttrainer.android.dati.Esercizio

/**
 * Anteprima degli esercizi letti da un CSV importato, con conferma prima di
 * aggiungerli alla lista corrente (equivalente di st.dataframe + bottone
 * "Importa esercizi nella lista" di app.py).
 */
@Composable
fun ImportaCsvAnteprimaDialog(
    esercizi: List<Esercizio>,
    onConferma: () -> Unit,
    onAnnulla: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onAnnulla,
        title = { Text(stringResource(R.string.import_csv_anteprima_titolo)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.import_csv_anteprima_conteggio, esercizi.size))
                LazyColumn(modifier = Modifier.heightIn(max = 360.dp)) {
                    items(esercizi, key = { it.uid }) { esercizio ->
                        ListItem(
                            headlineContent = { Text(esercizio.nome.ifBlank { "—" }) },
                            supportingContent = {
                                val dettaglio = listOfNotNull(
                                    esercizio.gruppo.takeIf { it.isNotBlank() },
                                    esercizio.ripetizioni.takeIf { it.isNotBlank() },
                                    esercizio.recupero.takeIf { it.isNotBlank() },
                                ).joinToString(" · ")
                                if (dettaglio.isNotBlank()) Text(dettaglio)
                            },
                        )
                        HorizontalDivider()
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onConferma) { Text(stringResource(R.string.import_csv_conferma)) }
        },
        dismissButton = {
            TextButton(onClick = onAnnulla) { Text(stringResource(R.string.azione_annulla)) }
        },
        modifier = Modifier.fillMaxWidth(),
    )
}
