package me.vattitude.morningbrief.ui

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.Cloud
import androidx.compose.material.icons.outlined.FlashOn
import androidx.compose.material.icons.outlined.GraphicEq
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Umbrella
import androidx.compose.material.icons.outlined.WbCloudy
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt
import me.vattitude.morningbrief.pipeline.PHONE_VOICE

fun clock(seconds: Double): String {
    val s = seconds.toInt().coerceAtLeast(0)
    return "%d:%02d".format(s / 60, s % 60)
}

@Composable
fun TodayScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val briefing by vm.briefing.collectAsState()
    val dates by vm.dates.collectAsState()
    val selected by vm.selected.collectAsState()
    val build by vm.build.collectAsState()
    val player by vm.player.collectAsState()
    val saved by vm.saved.collectAsState()
    val pack by vm.packInstalled.collectAsState()
    val context = LocalContext.current
    val t = Mb.t

    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.buildNow() }
    fun startBuild() {
        if (Build.VERSION.SDK_INT >= 33) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) else vm.buildNow()
    }

    val b = briefing
    val mine = player.date == b?.date
    val position = if (mine) player.position else 0.0
    val playing = mine && player.playing
    val voiceChanged = remember(b, saved, pack) { b != null && vm.voiceChanged(b, saved) }

    LazyColumn(modifier.fillMaxSize(), contentPadding = ScreenPadding) {
        item {
            val day = b?.date?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now()
            ScreenHeader(
                overline = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Overline(day.format(DateTimeFormatter.ofPattern("EEE · d MMM", Locale.ENGLISH)), Modifier.weight(1f))
                        b?.wx?.let { wx ->
                            Icon(weatherIcon(wx.code), null, Modifier.size(14.dp), tint = t.muted)
                            Spacer(Modifier.width(6.dp))
                            Overline("${wx.city} ${wx.now}°")
                        }
                    }
                },
                title = "Morning Brief",
                subtitle = if (b == null) "Your news, read aloud each morning." else summaryLine(b),
            )
        }

        if (build.running) item {
            Notice(Modifier.padding(top = 22.dp)) {
                Text("Making your briefing", style = Type.title, color = t.ink)
                Hint(build.step, Modifier.padding(top = 4.dp))
                LinearProgressIndicator(
                    progress = { build.fraction },
                    modifier = Modifier.fillMaxWidth().padding(top = 14.dp).height(6.dp),
                    color = t.ink, trackColor = t.track, strokeCap = StrokeCap.Round, gapSize = 0.dp, drawStopIndicator = {},
                )
                Hint("This takes a few minutes. You can leave the app.", Modifier.padding(top = 10.dp))
            }
        } else build.error?.let { err ->
            item {
                Notice(Modifier.padding(top = 22.dp)) {
                    Text("The last briefing couldn't be made", style = Type.title, color = t.error)
                    Text(err, Modifier.padding(top = 4.dp), style = Type.body, color = t.ink)
                }
            }
        }

        if (b != null && !build.running && voiceChanged) item {
            val (id, name) = vm.currentVoice(saved)
            val now = if (id == PHONE_VOICE) "the phone voice" else name
            val then = if (b.voiceId.startsWith("kokoro:")) b.voiceName else "the phone voice"
            Notice(Modifier.padding(top = 22.dp)) {
                Text("You've switched to $now", style = Type.title, color = t.ink)
                Text("This briefing was recorded with $then. Re-record it with the same stories, " +
                    "or the new voice starts with your next briefing.", Modifier.padding(top = 4.dp), style = Type.body, color = t.muted)
                PillButton("Re-record with $now", Modifier.padding(top = 14.dp)) { vm.revoice(b.date) }
            }
        }

        if (b == null) {
            item {
                Notice(Modifier.padding(top = 22.dp)) {
                    Text("Good morning", style = Type.title, color = t.ink)
                    Text("Morning Brief reads the news you choose and turns it into a short spoken briefing, " +
                        "made right here on your phone. Pick your sources and voice, or start with the defaults.",
                        Modifier.padding(top = 6.dp), style = Type.body, color = t.muted)
                    PillButton("Make my first briefing", Modifier.padding(top = 16.dp), enabled = !build.running) { startBuild() }
                }
            }
            return@LazyColumn
        }

        item {
            val current = b.cards.lastOrNull { mine && position >= it.start }
            val cover = current?.image ?: b.cards.firstOrNull { it.image != null }?.image
            Glass(Modifier.fillMaxWidth().padding(top = 22.dp), RoundedCornerShape(26.dp)) {
                Column(Modifier.padding(12.dp)) {
                    if (cover != null) {
                        AsyncImage(
                            model = cover, contentDescription = null, contentScale = ContentScale.Crop, colorFilter = Grayscale,
                            modifier = Modifier.fillMaxWidth().height(190.dp).clip(RoundedCornerShape(16.dp)).background(t.track),
                        )
                    }
                    Row(Modifier.padding(start = 4.dp, end = 4.dp, top = if (cover != null) 14.dp else 4.dp, bottom = 4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        InkCircle(if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow, if (playing) "Pause" else "Play",
                            size = 52.dp, enabled = player.ready) { vm.togglePlay() }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Progress(b, position) { vm.seekTo(it, play = playing) }
                            Row(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                                Text(clock(position), Modifier.weight(1f), style = Type.meta, color = t.muted)
                                Text(clock(b.duration), style = Type.meta, color = t.muted)
                            }
                        }
                    }
                }
            }
        }

        if (dates.size > 1) item {
            LazyRow(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(dates) { d -> Chip(dayLabel(d), selected = d == selected) { vm.select(d) } }
            }
        }

        for (section in b.sections) {
            val cards = b.cards.filter { it.section == section.key }
            if (cards.isEmpty()) continue
            item(key = "s:${section.key}") {
                val lead = b.chapters.firstOrNull { it.id == "section:${section.key}" }
                Row(
                    Modifier.fillMaxWidth().padding(top = 22.dp).clickable(enabled = lead != null) { lead?.let { vm.seekTo(it.start) } }
                        .padding(horizontal = 4.dp),
                ) {
                    Overline(section.title, Modifier.weight(1f), color = t.ink)
                    Overline(if (cards.size == 1) "1 story" else "${cards.size} stories")
                }
                GlassGroup(Modifier.padding(top = 10.dp)) {
                    cards.forEachIndexed { i, card ->
                        if (i > 0) Hairline()
                        StoryRow(card, current = mine && position >= card.start && position < card.end, playing = playing,
                            onPlay = { vm.seekTo(card.start) },
                            onOpen = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(card.url))) })
                    }
                }
            }
        }

        if (b.notes.isNotEmpty()) item {
            Column(Modifier.padding(top = 18.dp, start = 4.dp, end = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (n in b.notes) Hint(n)
            }
        }

        item {
            PillButton(
                if (b.date == LocalDate.now().toString()) "Make a fresh briefing" else "Make today's briefing",
                Modifier.fillMaxWidth().padding(top = 22.dp), filled = false, enabled = !build.running, icon = Icons.Outlined.Refresh,
            ) { startBuild() }
        }
    }
}

/** A glass card for status and prompts. */
@Composable
private fun Notice(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Glass(modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp)) { content() } }
}

/** "12 stories, five minutes. Light drizzle, high 21°." */
private fun summaryLine(b: Briefing): String {
    val n = b.cards.size
    val minutes = (b.duration / 60).roundToInt().coerceAtLeast(1)
    val words = listOf("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
    val m = words.getOrNull(minutes - 1) ?: "$minutes"
    var line = "${if (n == 1) "1 story" else "$n stories"}, $m minute${if (minutes == 1) "" else "s"}."
    b.wx?.let { line += " ${it.conditions.replaceFirstChar { c -> c.uppercase() }}, high ${it.high}°." }
    return line
}

private fun weatherIcon(code: Int): ImageVector = when (code) {
    0, 1 -> Icons.Outlined.WbSunny
    2 -> Icons.Outlined.WbCloudy
    in 51..67, in 80..82 -> Icons.Outlined.Umbrella
    in 71..77, 85, 86 -> Icons.Outlined.AcUnit
    in 95..99 -> Icons.Outlined.FlashOn
    else -> Icons.Outlined.Cloud
}

/** The progress bar, one segment per story; tap or drag to move through the briefing. */
@Composable
private fun Progress(b: Briefing, position: Double, onSeek: (Double) -> Unit) {
    val t = Mb.t
    val total = b.duration.coerceAtLeast(1.0)
    val marks = remember(b) {
        (listOf(0.0) + b.cards.map { it.start }.filter { it > 0.5 && it < total } + total).distinct().sorted()
    }
    var dragging by remember { mutableStateOf<Double?>(null) }
    val seek by rememberUpdatedState(onSeek)
    val shown = dragging ?: position
    Canvas(
        Modifier.fillMaxWidth().height(22.dp)
            .pointerInput(total) { detectTapGestures { seek((it.x / size.width).coerceIn(0f, 1f) * total) } }
            .pointerInput(total) {
                detectHorizontalDragGestures(
                    onDragStart = { dragging = (it.x / size.width).coerceIn(0f, 1f) * total },
                    onHorizontalDrag = { change, _ -> dragging = (change.position.x / size.width).coerceIn(0f, 1f) * total },
                    onDragEnd = { dragging?.let { seek(it) }; dragging = null },
                    onDragCancel = { dragging = null },
                )
            },
    ) {
        val gap = 3.dp.toPx()
        val h = 6.dp.toPx()
        val top = (size.height - h) / 2
        val usable = size.width - gap * (marks.size - 2)
        val r = CornerRadius(h / 2)
        var x = 0f
        for (i in 0 until marks.size - 1) {
            val w = (usable * (marks[i + 1] - marks[i]) / total).toFloat()
            drawRoundRect(t.ink.copy(alpha = if (t.dark) .18f else .12f), Offset(x, top), Size(w, h), r)
            val done = ((shown - marks[i]) / (marks[i + 1] - marks[i])).coerceIn(0.0, 1.0).toFloat()
            if (done > 0f) drawRoundRect(t.ink, Offset(x, top), Size(w * done, h), r)
            x += w + gap
        }
    }
}

@Composable
private fun StoryRow(card: Card, current: Boolean, playing: Boolean, onPlay: () -> Unit, onOpen: () -> Unit) {
    val t = Mb.t
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().clickable { open = !open }.padding(vertical = 14.dp).animateContentSize()) {
        Row(verticalAlignment = Alignment.Top) {
            Box(Modifier.width(40.dp).padding(top = 2.dp)) {
                if (current && playing) Icon(Icons.Outlined.GraphicEq, "Playing", Modifier.size(16.dp), tint = t.ink)
                else Text(clock(card.start), style = Type.meta, color = if (current) t.ink else t.muted)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(card.headline, style = Type.title, color = t.ink)
                val secs = (card.end - card.start).roundToInt()
                val meta = listOfNotNull(
                    card.source.ifBlank { null },
                    if (secs < 60) "${secs}s" else clock(secs.toDouble()),
                    card.also.size.takeIf { it > 0 }?.let { "+$it source${if (it == 1) "" else "s"}" },
                )
                Text(meta.joinToString(" · "), Modifier.padding(top = 5.dp), style = Type.meta, color = t.muted,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (card.image != null) {
                Spacer(Modifier.width(12.dp))
                AsyncImage(model = card.image, contentDescription = null, contentScale = ContentScale.Crop, colorFilter = Grayscale,
                    modifier = Modifier.size(56.dp).clip(RoundedCornerShape(12.dp)).background(t.track))
            }
        }
        if (open) {
            Column(Modifier.padding(start = 52.dp, top = 10.dp)) {
                Text(card.summary, style = Type.body, color = t.ink)
                if (card.also.isNotEmpty()) {
                    Hint("Also covered by ${card.also.joinToString(", ")}", Modifier.padding(top = 6.dp))
                }
                Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PillButton("Play", icon = Icons.Filled.PlayArrow, onClick = onPlay)
                    PillButton("Article", filled = false, icon = Icons.AutoMirrored.Outlined.OpenInNew, onClick = onOpen)
                }
            }
        }
    }
}

private fun dayLabel(date: String): String {
    val d = runCatching { LocalDate.parse(date) }.getOrNull() ?: return date
    val today = LocalDate.now()
    return when (d) {
        today -> "Today"
        today.minusDays(1) -> "Yesterday"
        else -> d.format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.ENGLISH))
    }
}
