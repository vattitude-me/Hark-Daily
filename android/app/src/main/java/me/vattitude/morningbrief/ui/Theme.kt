package me.vattitude.morningbrief.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import me.vattitude.morningbrief.R

/**
 * The v3 look (docs/ui-design/Morning Brief v3.dc.html): near-monochrome ink on a soft grey backdrop,
 * frosted glass panels, pill controls and small uppercase labels.
 */
@Immutable
data class Tokens(
    val bg: Color,
    val ink: Color,
    /** Text and icons on an ink fill. */
    val onInk: Color,
    val muted: Color,
    val line: Color,
    val glass: Color,
    val glassLine: Color,
    /** The well behind segmented controls and progress bars. */
    val track: Color,
    val error: Color,
    /** The backdrop's soft blobs, top left, right and bottom left. */
    val blobs: List<Color>,
    val dark: Boolean,
)

val LightTokens = Tokens(
    bg = Color(0xFFE9E9E5), ink = Color(0xFF0D0D0D), onInk = Color(0xFFF4F4F1), muted = Color(0xFF6C6C68),
    line = Color(0x14000000), glass = Color(0x73FFFFFF), glassLine = Color(0xD9FFFFFF), track = Color(0x0D000000),
    error = Color(0xFFB3261E), blobs = listOf(Color(0xFFBDBDB8), Color(0xFFC9C9C4), Color(0xFFB3B3AE)), dark = false,
)

val DarkTokens = Tokens(
    bg = Color(0xFF121211), ink = Color(0xFFEDEDE9), onInk = Color(0xFF121211), muted = Color(0xFF93938E),
    line = Color(0x17FFFFFF), glass = Color(0x0FFFFFFF), glassLine = Color(0x1CFFFFFF), track = Color(0x14FFFFFF),
    error = Color(0xFFF2B8B5), blobs = listOf(Color(0xFF2B2B28), Color(0xFF242422), Color(0xFF30302D)), dark = true,
)

val LocalTokens = staticCompositionLocalOf { LightTokens }

object Mb {
    val t: Tokens
        @Composable @ReadOnlyComposable get() = LocalTokens.current
}

val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
)

/** The few text sizes the design uses. Numbers are tabular so times and counts don't jiggle. */
object Type {
    val display = TextStyle(fontFamily = Inter, fontSize = 32.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.8).sp,
        lineHeight = 34.sp)
    val lead = TextStyle(fontFamily = Inter, fontSize = 15.sp, lineHeight = 21.sp)
    val body = TextStyle(fontFamily = Inter, fontSize = 15.sp, lineHeight = 20.sp)
    val title = TextStyle(fontFamily = Inter, fontSize = 15.sp, fontWeight = FontWeight.Medium, lineHeight = 19.5.sp)
    val value = TextStyle(fontFamily = Inter, fontSize = 14.sp, fontFeatureSettings = "tnum")
    val meta = TextStyle(fontFamily = Inter, fontSize = 12.sp, lineHeight = 16.sp, fontFeatureSettings = "tnum")
    val label = TextStyle(fontFamily = Inter, fontSize = 12.sp, letterSpacing = 0.24.sp, fontFeatureSettings = "tnum")
    val tiny = TextStyle(fontFamily = Inter, fontSize = 11.sp, fontFeatureSettings = "tnum")
}

private val Light = lightColorScheme(
    primary = LightTokens.ink, onPrimary = LightTokens.onInk,
    primaryContainer = Color(0xFFDADAD5), onPrimaryContainer = LightTokens.ink,
    secondary = LightTokens.ink, onSecondary = LightTokens.onInk,
    secondaryContainer = Color(0xFFDADAD5), onSecondaryContainer = LightTokens.ink,
    background = LightTokens.bg, onBackground = LightTokens.ink,
    surface = LightTokens.bg, onSurface = LightTokens.ink, onSurfaceVariant = LightTokens.muted,
    surfaceVariant = Color(0xFFDFDFDA), surfaceContainerLowest = Color(0xFFF7F7F4), surfaceContainerLow = Color(0xFFF2F2EF),
    surfaceContainer = Color(0xFFEFEFEB), surfaceContainerHigh = Color(0xFFF4F4F1), surfaceContainerHighest = Color(0xFFE4E4E0),
    outline = Color(0x40000000), outlineVariant = LightTokens.line,
    inverseSurface = LightTokens.ink, inverseOnSurface = LightTokens.onInk, inversePrimary = LightTokens.onInk,
    error = LightTokens.error, errorContainer = Color(0xFFF6DCDA), onErrorContainer = Color(0xFF410E0B),
)

private val Dark = darkColorScheme(
    primary = DarkTokens.ink, onPrimary = DarkTokens.onInk,
    primaryContainer = Color(0xFF2C2C2A), onPrimaryContainer = DarkTokens.ink,
    secondary = DarkTokens.ink, onSecondary = DarkTokens.onInk,
    secondaryContainer = Color(0xFF2C2C2A), onSecondaryContainer = DarkTokens.ink,
    background = DarkTokens.bg, onBackground = DarkTokens.ink,
    surface = DarkTokens.bg, onSurface = DarkTokens.ink, onSurfaceVariant = DarkTokens.muted,
    surfaceVariant = Color(0xFF262624), surfaceContainerLowest = Color(0xFF0C0C0B), surfaceContainerLow = Color(0xFF181817),
    surfaceContainer = Color(0xFF1C1C1B), surfaceContainerHigh = Color(0xFF222220), surfaceContainerHighest = Color(0xFF2A2A28),
    outline = Color(0x40FFFFFF), outlineVariant = DarkTokens.line,
    inverseSurface = DarkTokens.ink, inverseOnSurface = DarkTokens.onInk, inversePrimary = DarkTokens.onInk,
    error = DarkTokens.error, errorContainer = Color(0xFF5C1A16), onErrorContainer = Color(0xFFF9DEDC),
)

private fun Typography.inter(): Typography {
    fun TextStyle.i() = copy(fontFamily = Inter)
    return Typography(
        displayLarge.i(), displayMedium.i(), displaySmall.i(), headlineLarge.i(), headlineMedium.i(), headlineSmall.i(),
        titleLarge.i(), titleMedium.i(), titleSmall.i(), bodyLarge.i(), bodyMedium.i(), bodySmall.i(),
        labelLarge.i(), labelMedium.i(), labelSmall.i(),
    )
}

private val InterTypography = Typography().inter()

/** "light", "dark" or "system" (follow the phone). */
@Composable
fun isDark(appearance: String): Boolean = when (appearance) {
    "light" -> false
    "dark" -> true
    else -> isSystemInDarkTheme()
}

@Composable
fun MorningBriefTheme(appearance: String = "system", content: @Composable () -> Unit) {
    val dark = isDark(appearance)
    CompositionLocalProvider(LocalTokens provides if (dark) DarkTokens else LightTokens) {
        MaterialTheme(colorScheme = if (dark) Dark else Light, typography = InterTypography, content = content)
    }
}
