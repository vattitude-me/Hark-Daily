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
    val accent: Color = Color(0xFFF59E0B),
    val accentStrong: Color = Color(0xFFD97706),
    val accentInk: Color = Color(0xFF1F1300),
    val accentText: Color = Color(0xFFB45309),
    val accentSoft: Color = Color(0x21F59E0B),
    val accentLine: Color = Color(0x52D97706),
    val cardBg: Color = Color(0xFFFFFFFF),
    val playerBg: Color = Color(0xFFFFFFFF),
    val consoleDeckBg: Color = Color(0x080F172A),
    val teleprompterBg: Color = Color(0xFFFBFBFA),
)

val LightTokens = Tokens(
    bg = Color(0xFFF3F2EE),
    ink = Color(0xFF101828),
    onInk = Color(0xFFF4F4F1),
    muted = Color(0xFF667085),
    line = Color(0x140F172A),
    glass = Color(0x94FFFFFF),
    glassLine = Color(0xD9FFFFFF),
    track = Color(0x0F0F172A),
    error = Color(0xFFC0362C),
    blobs = listOf(Color(0x1FF59E0B), Color(0x146366F1), Color(0x143898D2)),
    dark = false,
    accent = Color(0xFFF59E0B),
    accentStrong = Color(0xFFD97706),
    accentInk = Color(0xFF1F1300),
    accentText = Color(0xFFB45309),
    accentSoft = Color(0x21F59E0B),
    accentLine = Color(0x52D97706),
    cardBg = Color(0xFFFFFFFF),
    playerBg = Color(0xFFFFFFFF),
    consoleDeckBg = Color(0x080F172A),
    teleprompterBg = Color(0xFFFBFBFA),
)

val DarkTokens = Tokens(
    bg = Color(0xFF0B0F17),
    ink = Color(0xFFF8FAFC),
    onInk = Color(0xFF101828),
    muted = Color(0xFF94A3B8),
    line = Color(0x14FFFFFF),
    glass = Color(0x99111827),
    glassLine = Color(0x1CFFFFFF),
    track = Color(0x1EFFFFFF),
    error = Color(0xFFF87171),
    blobs = listOf(Color(0x24F59E0B), Color(0x1F4F46E5), Color(0x1238BDF8)),
    dark = true,
    accent = Color(0xFFF59E0B),
    accentStrong = Color(0xFFFBBF24),
    accentInk = Color(0xFF1F1300),
    accentText = Color(0xFFFBBF24),
    accentSoft = Color(0x38F59E0B),
    accentLine = Color(0x66F59E0B),
    cardBg = Color(0xFF141C2C),
    playerBg = Color(0xFF131926),
    consoleDeckBg = Color(0x6B000000),
    teleprompterBg = Color(0xFF090D15),
)

fun categoryColor(section: String?): Color = when (section?.lowercase()) {
    "top" -> Color(0xFFB45309)
    "ai" -> Color(0xFF6355C7)
    "tech", "technology" -> Color(0xFF2F6F9F)
    "politics" -> Color(0xFFA8473F)
    "culture", "entertainment", "film" -> Color(0xFF9B4688)
    "science" -> Color(0xFF0F766E)
    "sport", "sports" -> Color(0xFF3E7B38)
    "custom" -> Color(0xFF5B5FC7)
    else -> Color(0xFF667085)
}

fun Tokens.categoryColor(section: String?): Color = me.vattitude.morningbrief.ui.categoryColor(section)

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
