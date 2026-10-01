package me.vattitude.morningbrief.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Light = lightColorScheme(
    primary = Color(0xFFB45309),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFDE7C3),
    onPrimaryContainer = Color(0xFF3B2003),
    secondary = Color(0xFF7C5E3C),
    secondaryContainer = Color(0xFFF3E3CF),
    background = Color(0xFFFFFBF5),
    surface = Color(0xFFFFFBF5),
    surfaceVariant = Color(0xFFF4ECE1),
    surfaceContainer = Color(0xFFF8F0E5),
    surfaceContainerHigh = Color(0xFFF3E9DC),
)

private val Dark = darkColorScheme(
    primary = Color(0xFFFBBF24),
    onPrimary = Color(0xFF3B2003),
    primaryContainer = Color(0xFF5C3A0A),
    onPrimaryContainer = Color(0xFFFDE7C3),
    secondary = Color(0xFFDCC3A3),
    secondaryContainer = Color(0xFF4A3A28),
    background = Color(0xFF17130F),
    surface = Color(0xFF17130F),
    surfaceVariant = Color(0xFF2A241D),
    surfaceContainer = Color(0xFF221D17),
    surfaceContainerHigh = Color(0xFF2C261F),
)

@Composable
fun MorningBriefTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
