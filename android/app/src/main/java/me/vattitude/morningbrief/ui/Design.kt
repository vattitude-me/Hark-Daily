package me.vattitude.morningbrief.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalMinimumInteractiveComponentSize
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.hypot

/** Photos are shown in black and white, like the rest of the page. */
val Grayscale = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0f) })

/** The soft grey backdrop the glass panels sit on. */
fun Modifier.backdrop(t: Tokens) = drawBehind {
    drawRect(t.bg)
    val d = hypot(size.width, size.height)
    for ((c, spot) in t.blobs.zip(listOf(Triple(.16f, .10f, .36f), Triple(.94f, .48f, .40f), Triple(.22f, .90f, .34f)))) {
        val (x, y, r) = spot
        drawRect(Brush.radialGradient(listOf(c, c.copy(alpha = 0f)), Offset(size.width * x, size.height * y), d * r))
    }
}

/** A frosted panel. */
@Composable
fun Glass(
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(22.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    val t = Mb.t
    Column(modifier.clip(shape).background(t.glass).border(1.dp, t.glassLine, shape), content = content)
}

/** A glass panel of rows separated by hairlines; put [Hairline] between rows. */
@Composable
fun GlassGroup(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) =
    Glass(modifier.fillMaxWidth()) { Column(Modifier.padding(horizontal = 14.dp), content = content) }

@Composable
fun Hairline(modifier: Modifier = Modifier) = Box(modifier.fillMaxWidth().height(1.dp).background(Mb.t.line))

/** Small uppercase text: the date above a title, a section's name. */
@Composable
fun Overline(text: String, modifier: Modifier = Modifier, color: Color = Mb.t.muted) =
    Text(text.uppercase(), modifier, style = Type.label, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)

/** The top of each tab: an overline, a large title and a line under it. */
@Composable
fun ScreenHeader(overline: @Composable () -> Unit, title: String, subtitle: String? = null) {
    Column {
        overline()
        Text(title, Modifier.padding(top = 10.dp), style = Type.display, color = Mb.t.ink)
        subtitle?.let { Text(it, Modifier.padding(top = 6.dp), style = Type.lead, color = Mb.t.muted) }
    }
}

/** A section's label above its panel, with an optional detail line and control on the right. */
@Composable
fun SectionLabel(
    text: String,
    modifier: Modifier = Modifier,
    detail: String? = null,
    end: @Composable RowScope.() -> Unit = {},
) {
    Row(modifier.fillMaxWidth().padding(top = 26.dp, bottom = 10.dp, start = 4.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Overline(text, color = Mb.t.ink)
            detail?.let { Text(it, Modifier.padding(top = 4.dp), style = Type.meta, color = Mb.t.muted) }
        }
        end()
    }
}

@Composable
private fun StepButton(icon: ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
    Box(Modifier.size(34.dp).clip(CircleShape).clickable(enabled = enabled, onClick = onClick), contentAlignment = Alignment.Center) {
        Icon(icon, label, Modifier.size(18.dp), tint = if (enabled) Mb.t.ink else Mb.t.muted.copy(alpha = .5f))
    }
}

/** − n + in a pill; 0 reads "Off". */
@Composable
fun PillStepper(n: Int, max: Int = 10, label: String = "stories", onChange: (Int) -> Unit) =
    PillStepper(if (n == 0) "Off" else "$n", n > 0, n < max, "Fewer $label", "More $label", { onChange(n - 1) }, { onChange(n + 1) })

@Composable
fun PillStepper(
    text: String,
    canLower: Boolean,
    canRaise: Boolean,
    lowerLabel: String,
    raiseLabel: String,
    onLower: () -> Unit,
    onRaise: () -> Unit,
) {
    val t = Mb.t
    Row(Modifier.height(36.dp).clip(CircleShape).background(t.glass).border(1.dp, t.glassLine, CircleShape),
        verticalAlignment = Alignment.CenterVertically) {
        StepButton(Icons.Outlined.Remove, lowerLabel, canLower, onLower)
        Text(text, Modifier.widthIn(min = 26.dp), style = Type.value, color = t.ink, textAlign = TextAlign.Center)
        StepButton(Icons.Outlined.Add, raiseLabel, canRaise, onRaise)
    }
}

/** A round on/off mark: filled with a tick when on. */
@Composable
fun CheckDot(checked: Boolean, modifier: Modifier = Modifier) {
    val t = Mb.t
    Box(
        modifier.size(24.dp).clip(CircleShape).background(if (checked) t.ink else Color.Transparent)
            .border(1.5.dp, if (checked) t.ink else t.ink.copy(alpha = .25f), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        if (checked) Icon(Icons.Outlined.Check, null, Modifier.size(14.dp), tint = t.onInk)
    }
}

/** Options in a pill well; the chosen one is filled with ink. */
@Composable
fun Segmented(
    options: List<String>,
    selected: Int,
    modifier: Modifier = Modifier,
    height: Dp = 34.dp,
    glass: Boolean = false,
    onSelect: (Int) -> Unit,
) {
    val t = Mb.t
    val well = if (glass) Modifier.background(t.glass).border(1.dp, t.glassLine, CircleShape) else Modifier.background(t.track)
    Row(modifier.fillMaxWidth().clip(CircleShape).then(well).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        options.forEachIndexed { i, label ->
            val on = i == selected
            Box(
                Modifier.weight(1f).height(height).clip(CircleShape).background(if (on) t.ink else Color.Transparent)
                    .clickable { onSelect(i) },
                contentAlignment = Alignment.Center,
            ) {
                Text(label, style = Type.value.copy(fontSize = Type.meta.fontSize * 13 / 12), color = if (on) t.onInk else t.muted,
                    maxLines = 1)
            }
        }
    }
}

/** The round ink button: play, follow, add. */
@Composable
fun InkCircle(
    icon: ImageVector,
    label: String,
    size: Dp = 50.dp,
    enabled: Boolean = true,
    busy: Boolean = false,
    onClick: () -> Unit,
) {
    val t = Mb.t
    Box(
        Modifier.size(size).clip(CircleShape).background(if (enabled) t.ink else t.ink.copy(alpha = .35f))
            .clickable(enabled = enabled && !busy, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (busy) CircularProgressIndicator(Modifier.size(size * .4f), color = t.onInk, strokeWidth = 2.dp)
        else Icon(icon, label, Modifier.size(size * .4f), tint = t.onInk)
    }
}

/** A pill button: ink-filled for the main action, glass for the rest. */
@Composable
fun PillButton(
    text: String,
    modifier: Modifier = Modifier,
    filled: Boolean = true,
    enabled: Boolean = true,
    busy: Boolean = false,
    icon: ImageVector? = null,
    onClick: () -> Unit,
) {
    val t = Mb.t
    val bg = if (filled) Modifier.background(if (enabled) t.ink else t.ink.copy(alpha = .35f))
    else Modifier.background(t.glass).border(1.dp, t.glassLine, CircleShape)
    val fg = if (filled) t.onInk else if (enabled) t.ink else t.muted
    Row(
        modifier.height(44.dp).clip(CircleShape).then(bg).clickable(enabled = enabled && !busy, onClick = onClick)
            .padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(16.dp), color = fg, strokeWidth = 2.dp)
            Spacer(Modifier.width(8.dp))
        } else if (icon != null) {
            Icon(icon, null, Modifier.size(18.dp), tint = fg)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = Type.value.copy(fontWeight = FontWeight.Medium), color = fg, maxLines = 1)
    }
}

/** A small glass pill to tap, such as a suggestion. */
@Composable
fun Chip(text: String, selected: Boolean = false, onClick: () -> Unit) {
    val t = Mb.t
    Box(
        Modifier.height(34.dp).clip(CircleShape)
            .then(if (selected) Modifier.background(t.ink) else Modifier.background(t.glass).border(1.dp, t.glassLine, CircleShape))
            .clickable(onClick = onClick).padding(horizontal = 14.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = Type.value.copy(fontSize = Type.meta.fontSize * 13 / 12), color = if (selected) t.onInk else t.ink, maxLines = 1)
    }
}

/** A pill-shaped text field on glass. */
@Composable
fun PillField(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    error: Boolean = false,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
) {
    val t = Mb.t
    BasicTextField(
        value = value, onValueChange = onChange, singleLine = true, modifier = modifier,
        textStyle = Type.body.copy(color = t.ink), cursorBrush = SolidColor(t.ink),
        keyboardOptions = keyboardOptions, keyboardActions = keyboardActions, visualTransformation = visualTransformation,
        decorationBox = { inner ->
            Row(
                Modifier.height(50.dp).clip(CircleShape).background(t.glass)
                    .border(1.dp, if (error) t.error else t.glassLine, CircleShape).padding(horizontal = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                icon?.let {
                    Icon(it, null, Modifier.size(18.dp), tint = t.muted)
                    Spacer(Modifier.width(10.dp))
                }
                Box(Modifier.weight(1f)) {
                    if (value.isEmpty()) Text(placeholder, style = Type.body, color = t.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    inner()
                }
            }
        },
    )
}

/** A row in a [GlassGroup]: a label, an optional value and caret, or anything on the right. */
@Composable
fun ListRow(
    label: String,
    modifier: Modifier = Modifier,
    detail: String? = null,
    value: String? = null,
    caret: Boolean = false,
    color: Color = Mb.t.ink,
    onClick: (() -> Unit)? = null,
    end: @Composable RowScope.() -> Unit = {},
) {
    val t = Mb.t
    Row(
        modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(vertical = if (detail != null) 12.dp else 15.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = Type.body, color = color)
            detail?.let { Text(it, Modifier.padding(top = 3.dp), style = Type.meta, color = t.muted) }
        }
        value?.let { Text(it, Modifier.padding(start = 12.dp), style = Type.value, color = t.muted, maxLines = 1) }
        end()
        if (caret) Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, null, Modifier.padding(start = 6.dp).size(18.dp), tint = t.muted)
    }
}

/** A switch in ink. */
@Composable
fun MbSwitch(checked: Boolean, onChange: (Boolean) -> Unit) {
    val t = Mb.t
    // The row around it is the touch target, so the switch needn't pad itself out to 48dp.
    CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides 0.dp) { Switch(
        checked = checked, onCheckedChange = onChange,
        colors = SwitchDefaults.colors(
            checkedTrackColor = t.ink, checkedThumbColor = t.onInk, checkedBorderColor = t.ink,
            uncheckedTrackColor = t.track, uncheckedThumbColor = t.muted, uncheckedBorderColor = t.ink.copy(alpha = .15f),
        ),
    ) }
}

/** Muted small print. */
@Composable
fun Hint(text: String, modifier: Modifier = Modifier, color: Color = Mb.t.muted, textAlign: TextAlign? = null) =
    Text(text, modifier, style = Type.meta, color = color, textAlign = textAlign)
