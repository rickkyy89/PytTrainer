package com.pyttrainer.android.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

private val SchemaColoriScuro = darkColorScheme(
    primary = TealPrimario,
    secondary = TealScuro,
    background = GrigioSuperficieScura,
)

private val SchemaColoriChiaro = lightColorScheme(
    primary = TealPrimario,
    secondary = TealScuro,
    background = GrigioSfondo,
)

/**
 * Tema Material 3 minimale dell'app: colore dinamico (Android 12+) quando
 * disponibile, altrimenti lo schema teal fisso sopra. Nessuna tipografia o
 * forma personalizzata in questa fase (skeleton): arriveranno con le
 * schermate vere.
 */
@Composable
fun PytTrainerTheme(
    usaTemaScuro: Boolean = isSystemInDarkTheme(),
    coloreDinamico: Boolean = true,
    contenuto: @Composable () -> Unit,
) {
    val schemaColori = when {
        coloreDinamico && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val contesto = LocalContext.current
            if (usaTemaScuro) dynamicDarkColorScheme(contesto) else dynamicLightColorScheme(contesto)
        }
        usaTemaScuro -> SchemaColoriScuro
        else -> SchemaColoriChiaro
    }

    MaterialTheme(
        colorScheme = schemaColori,
        content = contenuto,
    )
}
