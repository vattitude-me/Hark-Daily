package me.vattitude.morningbrief.ui

import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.lazy.LazyItemScope
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material.icons.outlined.Umbrella
import androidx.compose.material.icons.outlined.WbCloudy
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import kotlinx.coroutines.launch
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.material3.TextButton
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.IconButton
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.RecordVoiceOver
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.border
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.ColumnScope
import kotlinx.coroutines.delay
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
    val briefingMode by vm.briefingMode.collectAsState()
    val packLoadingDate by vm.packLoadingDate.collectAsState()
    val dates by vm.dates.collectAsState()
    val selected by vm.selected.collectAsState()
    val build by vm.build.collectAsState()
    val player by vm.player.collectAsState()
    val saved by vm.saved.collectAsState()
    val pack by vm.packInstalled.collectAsState()
    val isAdmin by vm.isAdmin.collectAsState()
    val reported by vm.reported.collectAsState()
    var reporting by remember { mutableStateOf<Pair<Card, String>?>(null) }
    reporting?.let { (card, date) -> ReportDialog(vm, card, date) { reporting = null } }
    val context = LocalContext.current
    val t = Mb.t

    var latestNoticeDismissed by remember(briefing?.date) { mutableStateOf(false) }
    var voiceNoticeDismissed by remember(briefing, saved, pack) { mutableStateOf(false) }

    LaunchedEffect(briefing) {
        if (briefing != null) vm.clearBuildError()
    }
    LaunchedEffect(build.error) {
        if (build.error != null) {
            delay(10_000)
            vm.clearBuildError()
        }
    }

    val b = briefing
    val mine = player.date == b?.date
    val position = if (mine) player.position else 0.0
    val playing = mine && player.playing
    val voiceChanged = remember(b, saved, pack) { b != null && vm.voiceChanged(b, saved) }
    val current = b?.cards?.firstOrNull { mine && position >= it.start && position < it.end }
    val chapter = b?.chapters?.lastOrNull { mine && position >= it.start }

    val list = rememberLazyListState()
    val density = LocalDensity.current
    /** Where things are in the list: item indexes by key, and each story's offset within its section. */
    val index = remember { HashMap<String, Int>() }
    val rowTops = remember { HashMap<String, Int>() }
    var touchedAt by remember { mutableLongStateOf(0L) }
    val stillPlaying by rememberUpdatedState(playing)
    LaunchedEffect(list) {
        list.interactionSource.interactions.collect { if (it is DragInteraction.Start) touchedAt = SystemClock.uptimeMillis() }
    }
    // Follow along: bring the story being read into view, unless the reader scrolled in the last few seconds.
    LaunchedEffect(current?.id) {
        val card = current ?: return@LaunchedEffect
        if (!stillPlaying || SystemClock.uptimeMillis() - touchedAt < 8_000) return@LaunchedEffect
        val i = index["s:${card.section}"] ?: return@LaunchedEffect
        val margin = with(density) { 120.dp.roundToPx() }
        list.animateScrollToItem(i, ((rowTops[card.id] ?: 0) - margin).coerceAtLeast(0))
    }
    // The floating player shows once the player card's controls scroll out of sight.
    LaunchedEffect(list) {
        val controls = with(density) { 150.dp.roundToPx() }
        snapshotFlow {
            val hero = index["hero"]
            val info = list.layoutInfo
            hero == null || info.visibleItemsInfo.any { it.index == hero && it.offset + it.size - controls > info.viewportStartOffset }
        }.collect { vm.heroVisible.value = it }
    }
    DisposableEffect(Unit) { onDispose { vm.heroVisible.value = true } }
    val showHero by vm.showHero.collectAsState()
    LaunchedEffect(showHero) { if (showHero > 0) list.animateScrollToItem(0) }

    LazyColumn(modifier.fillMaxSize(), state = list, contentPadding = screenPadding()) {
        var count = 0
        fun entry(key: String? = null, content: @Composable LazyItemScope.() -> Unit) {
            key?.let { index[it] = count }
            count++
            item(key = key, content = content)
        }
        entry {
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
                title = "Hark Daily",
                subtitle = if (b == null) "The news you hear, not just read." else summaryLine(b),
            )
        }


        if (build.running) entry {
            Notice(Modifier.padding(top = 22.dp)) {
                Text("Making your brief", style = Type.title, color = t.ink)
                Hint(build.step, Modifier.padding(top = 4.dp))
                LinearProgressIndicator(
                    progress = { build.fraction },
                    modifier = Modifier.fillMaxWidth().padding(top = 14.dp).height(6.dp),
                    color = t.ink, trackColor = t.track, strokeCap = StrokeCap.Round, gapSize = 0.dp, drawStopIndicator = {},
                )
                Hint("This takes a few minutes. Feel free to leave the app; it keeps going.", Modifier.padding(top = 10.dp))
            }
        } else if (isAdmin && b == null) build.error?.let { err ->
            entry {
                Notice(Modifier.padding(top = 22.dp), onDismiss = { vm.clearBuildError() }) {
                    Text("Your last brief couldn't be made", style = Type.title, color = t.error)
                    Text(err, Modifier.padding(top = 4.dp), style = Type.body, color = t.ink)
                }
            }
        }

        if (b != null && !build.running && voiceChanged && !voiceNoticeDismissed) entry {
            val (id, name) = vm.currentVoice(saved)
            val now = if (id == PHONE_VOICE) "the phone voice" else name
            val then = if (b.voiceId.startsWith("kokoro:")) b.voiceName else "the phone voice"
            Notice(Modifier.padding(top = 22.dp), onDismiss = { voiceNoticeDismissed = true }) {
                Text("You've switched to $now", style = Type.title, color = t.ink)
                Text("This brief was recorded with $then. Re-record it with the same stories, " +
                    "or the new voice starts with your next brief.", Modifier.padding(top = 4.dp), style = Type.body, color = t.muted)
                PillButton("Re-record with $now", Modifier.padding(top = 14.dp)) { vm.revoice(b.date) }
            }
        }

        if (b == null) {
            entry {
                if (selected != null && selected == packLoadingDate) {
                    Notice(Modifier.padding(top = 22.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp), color = t.ink, strokeWidth = 2.dp,
                            )
                            Text("Checking for today's briefing", Modifier.padding(start = 12.dp), style = Type.title, color = t.ink)
                        }
                        Hint("Loading the latest audio and stories.", Modifier.padding(top = 6.dp))
                    }
                } else {
                    Notice(Modifier.padding(top = 22.dp)) {
                        Text("Today's brief isn't ready yet", style = Type.title, color = t.ink)
                        Text("It's recorded once each morning for everyone listening, so there's nothing to build here. " +
                            "Check back in a moment.",
                            Modifier.padding(top = 6.dp), style = Type.body, color = t.muted)
                        PillButton("Check again", Modifier.padding(top = 16.dp), filled = false) { vm.refreshPack() }
                    }
                }
            }
            return@LazyColumn
        }

        // The night's recording may not be out yet: the most recent day stands in for today.
        val today = LocalDate.now().toString()
        if (b.date != today && !latestNoticeDismissed) entry {
            val day = runCatching { LocalDate.parse(b.date) }.getOrNull()
                ?.format(DateTimeFormatter.ofPattern("EEE · d MMM", Locale.ENGLISH)) ?: b.date
            Notice(Modifier.padding(top = 22.dp), onDismiss = { latestNoticeDismissed = true }) {
                Text("Showing the latest brief, from $day", style = Type.title, color = t.ink)
                Text("Today's recording isn't out yet. This is the most recent one, in your usual topics. " +
                    "It'll switch over on its own.",
                    Modifier.padding(top = 4.dp), style = Type.body, color = t.muted)
                PillButton("Check again", Modifier.padding(top = 14.dp), filled = false) { vm.refreshPack() }
            }
        }

        entry("hero") {
            val cover = (current ?: b.cards.lastOrNull { mine && position >= it.start })?.image
                ?: b.cards.firstOrNull { it.image != null }?.image
            val section = (current?.section ?: chapter?.section)?.let { k -> b.sections.firstOrNull { it.key == k }?.title }
            val state = when {
                !mine || (position < 0.5 && !playing) -> "Ready · ${b.cards.size} stories"
                playing -> listOfNotNull("Now playing", section).joinToString(" · ")
                else -> listOfNotNull("Paused", section).joinToString(" · ")
            }
            val title = current?.headline ?: chapter?.title?.takeIf { mine && it.isNotBlank() } ?: b.title
            val isRapid = b.isRapid
            val currentIdx = b.cards.indexOfFirst { current != null && it.id == current.id }.takeIf { it >= 0 }

            val horizonColor = if (isRapid) Color(0xFFFBBF24) else t.accent
            val deckBgModifier = if (t.dark) {
                Modifier.background(
                    Brush.verticalGradient(listOf(Color(0xFF131926), Color(0xFF0C1018)))
                )
            } else {
                Modifier.background(Color.White)
            }

            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 22.dp)
                    .shadow(
                        elevation = if (playing) 16.dp else 4.dp,
                        shape = RoundedCornerShape(26.dp),
                        ambientColor = if (playing) t.accent.copy(alpha = 0.35f) else Color.Black.copy(alpha = 0.15f),
                        spotColor = if (playing) t.accent.copy(alpha = 0.45f) else Color.Black.copy(alpha = 0.2f),
                    )
                    .clip(RoundedCornerShape(26.dp))
                    .then(deckBgModifier)
                    .border(
                        1.dp,
                        if (playing) t.accent.copy(alpha = 0.55f) else if (t.dark) Color(0x22FFFFFF) else Color(0x140F172A),
                        RoundedCornerShape(26.dp)
                    )
                    .drawBehind {
                        val stroke = 3.5.dp.toPx()
                        drawLine(
                            color = horizonColor,
                            start = Offset(0f, stroke / 2),
                            end = Offset(size.width, stroke / 2),
                            strokeWidth = stroke
                        )
                    }
            ) {
                Column(Modifier.padding(16.dp)) {
                    // Briefing Edition Switcher: Full Brief vs ⚡ Rapid Fire
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(CircleShape)
                            .background(if (t.dark) Color(0x66000000) else Color(0x0C0F172A))
                            .border(1.dp, if (t.dark) Color(0x1AFFFFFF) else Color(0x140F172A), CircleShape)
                            .padding(3.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        val fullOn = !isRapid
                        Row(
                            Modifier
                                .weight(1f)
                                .height(34.dp)
                                .clip(CircleShape)
                                .background(if (fullOn) t.accent else Color.Transparent)
                                .clickable { vm.setBriefingMode("full") }
                                .padding(horizontal = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            Icon(
                                Icons.Outlined.WbSunny,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = if (fullOn) t.accentInk else t.muted
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "Full Brief",
                                style = Type.value.copy(fontSize = 12.sp, fontWeight = if (fullOn) FontWeight.Bold else FontWeight.Medium),
                                color = if (fullOn) t.accentInk else t.muted
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "~10 min",
                                style = Type.tiny,
                                color = if (fullOn) t.accentInk.copy(alpha = 0.8f) else t.muted.copy(alpha = 0.7f)
                            )
                        }

                        val rapidOn = isRapid
                        Row(
                            Modifier
                                .weight(1f)
                                .height(34.dp)
                                .clip(CircleShape)
                                .background(if (rapidOn) t.accent else Color.Transparent)
                                .clickable { vm.setBriefingMode("rapid") }
                                .padding(horizontal = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            Icon(
                                Icons.Outlined.FlashOn,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = if (rapidOn) t.accentInk else Color(0xFFF59E0B)
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "Rapid Fire",
                                style = Type.value.copy(fontSize = 12.sp, fontWeight = if (rapidOn) FontWeight.Bold else FontWeight.Medium),
                                color = if (rapidOn) t.accentInk else t.ink
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "⚡ Top 5 · 1.1x",
                                style = Type.tiny.copy(fontWeight = FontWeight.Bold),
                                color = if (rapidOn) t.accentInk.copy(alpha = 0.9f) else Color(0xFFB45309)
                            )
                        }
                    }

                    Spacer(Modifier.height(14.dp))

                    // Hero Top: Art + Heading + Actions
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            Modifier
                                .size(58.dp)
                                .clip(RoundedCornerShape(14.dp))
                                .background(t.track)
                                .border(1.dp, t.line, RoundedCornerShape(14.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            if (cover != null) {
                                AsyncImage(
                                    model = cover,
                                    contentDescription = null,
                                    contentScale = ContentScale.Crop,
                                    colorFilter = if (saved.colorPhotos) null else Grayscale,
                                    modifier = Modifier.fillMaxSize()
                                )
                            } else {
                                Icon(Icons.Outlined.GraphicEq, null, Modifier.size(24.dp), tint = t.accent)
                            }
                        }

                        Spacer(Modifier.width(12.dp))

                        Column(Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    Modifier
                                        .clip(CircleShape)
                                        .background(if (playing) t.accentSoft else t.track)
                                        .padding(horizontal = 7.dp, vertical = 2.dp)
                                ) {
                                    Text(
                                        if (playing) "NOW PLAYING" else if (!mine || position < 0.5) "READY" else "PAUSED",
                                        style = Type.tiny.copy(fontWeight = FontWeight.Bold),
                                        color = if (playing) t.accentText else t.muted
                                    )
                                }
                                if (section != null) {
                                    Spacer(Modifier.width(6.dp))
                                    Text(
                                        section.uppercase(),
                                        style = Type.tiny.copy(fontWeight = FontWeight.SemiBold),
                                        color = t.muted,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                            }
                            Text(
                                title,
                                modifier = Modifier.padding(top = 4.dp),
                                style = Type.title.copy(fontWeight = FontWeight.Bold),
                                color = t.ink,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                        }

                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            if (b.voiceName.isNotBlank()) {
                                Row(
                                    Modifier
                                        .clip(CircleShape)
                                        .background(t.glass)
                                        .border(1.dp, t.glassLine, CircleShape)
                                        .padding(horizontal = 8.dp, vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Outlined.RecordVoiceOver, null, Modifier.size(12.dp), tint = t.accent)
                                    Spacer(Modifier.width(4.dp))
                                    Text(b.voiceName, style = Type.tiny.copy(fontWeight = FontWeight.Medium), color = t.ink)
                                }
                            }
                            current?.url?.takeIf { it.isNotBlank() }?.let { url ->
                                Row(
                                    Modifier
                                        .clip(CircleShape)
                                        .background(t.accentSoft)
                                        .border(1.dp, t.accentLine, CircleShape)
                                        .clickable { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                                        .padding(horizontal = 8.dp, vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text("Article", style = Type.tiny.copy(fontWeight = FontWeight.SemiBold), color = t.accentText)
                                    Spacer(Modifier.width(3.dp))
                                    Icon(Icons.AutoMirrored.Outlined.OpenInNew, null, Modifier.size(10.dp), tint = t.accentText)
                                }
                            }
                        }
                    }

                    Spacer(Modifier.height(14.dp))

                    // Recessed Acoustic Console Deck
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(18.dp))
                            .background(t.consoleDeckBg)
                            .border(1.dp, if (t.dark) Color(0x14FFFFFF) else Color(0x0F0F172A), RoundedCornerShape(18.dp))
                            .padding(14.dp)
                    ) {
                        Column {
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(clock(position), style = Type.value.copy(fontWeight = FontWeight.Bold), color = t.accentText)
                                    Text(" / ", style = Type.meta, color = t.muted)
                                    Text("-" + clock((b.duration - position).coerceAtLeast(0.0)), style = Type.meta, color = t.muted)
                                }
                                val countText = if (currentIdx != null) "Story ${currentIdx + 1} of ${b.cards.size}" else "${b.cards.size} stories"
                                Overline(countText, color = t.muted)
                            }

                            Progress(b, position, Modifier.padding(top = 10.dp)) { vm.seekTo(it, play = playing || !mine) }

                            Spacer(Modifier.height(10.dp))

                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    Modifier
                                        .size(38.dp)
                                        .clip(CircleShape)
                                        .clickable { vm.skip(-15) },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text("-15", style = Type.tiny.copy(fontWeight = FontWeight.Bold), color = t.ink)
                                }

                                Skip(Icons.Filled.SkipPrevious, "Previous story", enabled = mine) { vm.jump(forward = false) }

                                JewelPlayButton(
                                    icon = if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                                    label = if (playing) "Pause" else "Play",
                                    size = 56.dp,
                                    enabled = player.ready
                                ) { vm.togglePlay() }

                                Skip(Icons.Filled.SkipNext, "Next story", enabled = player.ready) {
                                    if (mine) vm.jump(forward = true) else b.cards.firstOrNull()?.let { vm.seekTo(it.start) }
                                }

                                Box(
                                    Modifier
                                        .size(38.dp)
                                        .clip(CircleShape)
                                        .clickable { vm.skip(30) },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text("+30", style = Type.tiny.copy(fontWeight = FontWeight.Bold), color = t.ink)
                                }
                            }

                            Spacer(Modifier.height(10.dp))

                            val speeds = if (isRapid) listOf(1.0f, 1.1f, 1.25f, 1.5f) else listOf(0.8f, 1.0f, 1.25f, 1.5f)
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Center,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(
                                    Modifier
                                        .clip(CircleShape)
                                        .background(t.track)
                                        .border(1.dp, t.line, CircleShape)
                                        .padding(2.dp),
                                    horizontalArrangement = Arrangement.spacedBy(3.dp)
                                ) {
                                    for (s in speeds) {
                                        val active = Math.abs(player.speed - s) < 0.05f
                                        val label = "${s}x"
                                        Box(
                                            Modifier
                                                .height(26.dp)
                                                .clip(CircleShape)
                                                .background(if (active) t.accent else Color.Transparent)
                                                .clickable { vm.setPlaybackSpeed(s) }
                                                .padding(horizontal = 9.dp),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Text(
                                                label,
                                                style = Type.tiny.copy(fontWeight = if (active) FontWeight.Bold else FontWeight.Medium),
                                                color = if (active) t.accentInk else t.muted
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Integrated Read Along Teleprompter Visor
                    var transcriptExpanded by remember { mutableStateOf(false) }
                    val readText = current?.summary?.ifBlank { null } ?: current?.headline ?: "Tap play to listen and read along."

                    Spacer(Modifier.height(12.dp))

                    Box(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(t.teleprompterBg)
                            .border(1.dp, if (t.dark) Color(0x18FFFFFF) else Color(0x0F0F172A), RoundedCornerShape(16.dp))
                            .clickable { transcriptExpanded = !transcriptExpanded }
                            .padding(14.dp)
                    ) {
                        Column {
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Box(
                                        Modifier
                                            .size(7.dp)
                                            .clip(CircleShape)
                                            .background(t.accent)
                                    )
                                    Spacer(Modifier.width(6.dp))
                                    Text(
                                        "READ ALONG",
                                        style = Type.tiny.copy(fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp),
                                        color = t.accentText
                                    )
                                    Spacer(Modifier.width(6.dp))
                                    Text("Follows narrator", style = Type.tiny, color = t.muted)
                                }
                                Text(
                                    if (transcriptExpanded) "Collapse" else "Full text",
                                    style = Type.tiny.copy(fontWeight = FontWeight.SemiBold),
                                    color = t.accentText
                                )
                            }
                            Spacer(Modifier.height(6.dp))
                            Text(
                                readText,
                                style = Type.body.copy(fontSize = 13.5.sp, lineHeight = 19.sp),
                                color = t.ink,
                                maxLines = if (transcriptExpanded) 20 else 2,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
            }
        }

        if (dates.size > 1) entry {
            LazyRow(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(dates) { d -> Chip(dayLabel(d), selected = d == selected) { vm.select(d) } }
            }
        }

        for (section in b.sections) {
            val cards = b.cards.filter { it.section == section.key }
            if (cards.isEmpty()) continue
            entry("s:${section.key}") {
                val lead = b.chapters.firstOrNull { it.id == "section:${section.key}" }
                val here = current?.section == section.key
                val holder = remember { arrayOfNulls<LayoutCoordinates>(1) }
                Column(Modifier.onGloballyPositioned { holder[0] = it }) {
                    Row(
                        Modifier.fillMaxWidth().padding(top = 22.dp).clip(RoundedCornerShape(8.dp))
                            .clickable(enabled = lead != null) { lead?.let { vm.seekTo(it.start) } }
                            .padding(horizontal = 4.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Overline(section.title, Modifier.weight(1f), color = t.ink)
                        if (here) {
                            Box(Modifier.size(6.dp).clip(CircleShape).background(t.accent))
                            Spacer(Modifier.width(6.dp))
                            Overline(if (playing) "Playing" else "Paused", color = t.accentText)
                        } else {
                            Overline(if (cards.size == 1) "1 story" else "${cards.size} stories")
                        }
                    }
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        cards.forEach { card ->
                            StoryRow(
                                card, current = card.id == current?.id, playing = playing,
                                colorPhotos = saved.colorPhotos,
                                modifier = Modifier.onGloballyPositioned { c ->
                                    holder[0]?.takeIf { it.isAttached && c.isAttached }
                                        ?.let { rowTops[card.id] = it.localPositionOf(c, Offset.Zero).y.roundToInt() }
                                },
                                onPlay = { vm.seekTo(card.start) },
                                onOpen = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(card.url))) },
                                reported = card.id in reported,
                                onReport = { reporting = card to b.date },
                            )
                        }
                    }
                }
            }
        }

        if (b.notes.isNotEmpty()) entry {
            Column(Modifier.padding(top = 18.dp, start = 4.dp, end = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (n in b.notes) Hint(n)
            }
        }
    }
}

/** Previous or next story, beside the play button. */
@Composable
private fun Skip(icon: ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
    val t = Mb.t
    Icon(icon, label, Modifier.size(44.dp).clip(CircleShape).clickable(enabled = enabled, onClick = onClick).padding(9.dp),
        tint = if (enabled) t.ink else t.muted.copy(alpha = .5f))
}

/** A glass card for status and prompts. */
@Composable
private fun Notice(
    modifier: Modifier = Modifier,
    onDismiss: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    Glass(modifier.fillMaxWidth()) {
        Box(Modifier.fillMaxWidth().padding(18.dp)) {
            Column(Modifier.fillMaxWidth().padding(end = if (onDismiss != null) 28.dp else 0.dp)) {
                content()
            }
            if (onDismiss != null) {
                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.TopEnd).size(24.dp)
                ) {
                    Icon(
                        Icons.Outlined.Close,
                        contentDescription = "Dismiss",
                        tint = Mb.t.muted,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }
    }
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

/** The progress bar, one segment per story, with a thumb to drag; tap or drag to move through the briefing. */
@Composable
private fun Progress(b: Briefing, position: Double, modifier: Modifier = Modifier, onSeek: (Double) -> Unit) {
    val t = Mb.t
    val total = b.duration.coerceAtLeast(1.0)
    val marks = remember(b) {
        (listOf(0.0) + b.cards.map { it.start }.filter { it > 0.5 && it < total } + total).distinct().sorted()
    }
    var dragging by remember { mutableStateOf<Double?>(null) }
    val seek by rememberUpdatedState(onSeek)
    val shown = dragging ?: position
    Canvas(
        modifier.fillMaxWidth().height(32.dp)
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
        var thumb = 0f
        for (i in 0 until marks.size - 1) {
            val w = (usable * (marks[i + 1] - marks[i]) / total).toFloat()
            drawRoundRect(t.ink.copy(alpha = if (t.dark) .18f else .12f), Offset(x, top), Size(w, h), r)
            val done = ((shown - marks[i]) / (marks[i + 1] - marks[i])).coerceIn(0.0, 1.0).toFloat()
            if (done > 0f) {
                drawRoundRect(t.accent, Offset(x, top), Size(w * done, h), r)
                thumb = x + w * done
            }
            x += w + gap
        }
        val radius = (if (dragging != null) 10.dp else 7.dp).toPx()
        val cx = thumb.coerceIn(radius, size.width - radius)
        drawCircle(t.accent, radius, Offset(cx, size.height / 2))
        drawCircle(t.accentInk, radius * .38f, Offset(cx, size.height / 2))
    }
}

/**
 * One story card styled in Hark Daily's Editorial Broadsheet layout.
 * Features a 4dp category colored spine, amber accent highlight when playing,
 * expandable summary transcript, and quick play/article actions.
 */
@Composable
private fun StoryRow(
    card: Card,
    current: Boolean,
    playing: Boolean,
    colorPhotos: Boolean = false,
    modifier: Modifier = Modifier,
    onPlay: () -> Unit,
    onOpen: () -> Unit,
    reported: Boolean = false,
    onReport: () -> Unit = {},
) {
    val t = Mb.t
    var open by remember(current) { mutableStateOf(current) }
    val spineColor = t.categoryColor(card.section)
    val cardBg = if (current) {
        if (t.dark) Color(0xFF161F2E) else Color(0xFFFFFBEB)
    } else {
        t.cardBg
    }
    val borderColor = if (current) {
        if (playing) t.accent else t.accent.copy(alpha = 0.6f)
    } else {
        t.line
    }

    Box(
        modifier
            .fillMaxWidth()
            .shadow(
                elevation = if (current && playing) 8.dp else if (current) 3.dp else 1.dp,
                shape = RoundedCornerShape(16.dp),
                ambientColor = if (current) t.accent.copy(alpha = 0.25f) else Color.Black.copy(alpha = 0.05f),
                spotColor = if (current) t.accent.copy(alpha = 0.35f) else Color.Black.copy(alpha = 0.08f)
            )
            .clip(RoundedCornerShape(16.dp))
            .background(cardBg)
            .border(if (current) 1.5.dp else 1.dp, borderColor, RoundedCornerShape(16.dp))
            .drawBehind {
                val spineWidth = 4.dp.toPx()
                drawRect(
                    color = spineColor,
                    topLeft = Offset(0f, 0f),
                    size = Size(spineWidth, size.height)
                )
            }
            .clickable { open = !open }
            .animateContentSize()
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 14.dp, top = 14.dp, bottom = 14.dp)
        ) {
            Row(verticalAlignment = Alignment.Top) {
                // Play Button
                Column(Modifier.width(38.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        Modifier
                            .size(34.dp)
                            .clip(CircleShape)
                            .background(if (current) t.accent else t.track)
                            .border(1.dp, if (current) t.accentStrong else t.line, CircleShape)
                            .clickable(onClickLabel = "Play from this story", onClick = onPlay),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            if (current && playing) Icons.Outlined.GraphicEq else Icons.Filled.PlayArrow,
                            contentDescription = if (current && playing) "Playing" else "Play from here",
                            modifier = Modifier.size(16.dp),
                            tint = if (current) t.accentInk else t.ink
                        )
                    }
                    Text(
                        clock(card.start),
                        Modifier.padding(top = 4.dp),
                        style = Type.tiny.copy(fontWeight = if (current) FontWeight.Bold else FontWeight.Normal),
                        color = if (current) t.accentText else t.muted
                    )
                }

                Spacer(Modifier.width(12.dp))

                // Middle Text: Category & status overline + Headline + Metadata
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            card.section.uppercase(),
                            style = Type.tiny.copy(fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.6.sp),
                            color = spineColor
                        )
                        if (current) {
                            Spacer(Modifier.width(6.dp))
                            Box(
                                Modifier
                                    .clip(CircleShape)
                                    .background(t.accentSoft)
                                    .padding(horizontal = 6.dp, vertical = 2.dp)
                            ) {
                                Text(
                                    if (playing) "PLAYING" else "PAUSED",
                                    style = Type.tiny.copy(fontSize = 9.sp, fontWeight = FontWeight.Bold),
                                    color = t.accentText
                                )
                            }
                        }
                    }

                    Text(
                        card.headline,
                        modifier = Modifier.padding(top = 2.dp),
                        style = Type.title.copy(fontSize = 15.sp, fontWeight = if (current) FontWeight.Bold else FontWeight.SemiBold),
                        color = t.ink
                    )

                    val secs = (card.end - card.start).roundToInt()
                    val meta = listOfNotNull(
                        card.source.ifBlank { null },
                        (if (secs < 60) "${secs}s" else clock(secs.toDouble())) + " audio",
                        card.also.size.takeIf { it > 0 }?.let { "+$it source${if (it == 1) "" else "s"}" },
                    )
                    Text(
                        meta.joinToString(" · "),
                        Modifier.padding(top = 4.dp),
                        style = Type.meta,
                        color = t.muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }

                if (card.image != null) {
                    Spacer(Modifier.width(12.dp))
                    AsyncImage(
                        model = card.image,
                        contentDescription = null,
                        contentScale = ContentScale.Crop,
                        colorFilter = if (colorPhotos) null else Grayscale,
                        modifier = Modifier
                            .size(54.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(t.track)
                            .border(1.dp, t.line, RoundedCornerShape(12.dp))
                    )
                }
            }

            if (open) {
                Column(Modifier.padding(start = 50.dp, top = 10.dp)) {
                    Text(
                        card.summary,
                        style = Type.body.copy(fontSize = 13.5.sp, lineHeight = 19.sp),
                        color = t.ink
                    )
                    if (card.also.isNotEmpty()) {
                        Hint("Also covered by ${card.also.joinToString(", ")}", Modifier.padding(top = 6.dp))
                    }
                    Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (!current) PillButton("Play from here", icon = Icons.Filled.PlayArrow, onClick = onPlay)
                        PillButton("Article", filled = false, icon = Icons.AutoMirrored.Outlined.OpenInNew, onClick = onOpen)
                    }
                    // Report summary link
                    Row(
                        Modifier
                            .padding(top = 10.dp)
                            .clip(CircleShape)
                            .clickable(enabled = !reported, onClickLabel = "Report this summary", onClick = onReport)
                            .padding(vertical = 4.dp, horizontal = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Outlined.Flag, null, Modifier.size(13.dp), tint = t.muted)
                        Spacer(Modifier.width(5.dp))
                        Text(if (reported) "Reported. Thanks" else "Report this summary", style = Type.meta, color = t.muted)
                    }
                }
            }
        }
    }
}

private val REPORT_REASONS = listOf(
    "inaccurate" to "Wrong or misleading",
    "offensive" to "Offensive or harmful",
    "broken" to "Doesn't match the article",
    "other" to "Something else",
)

/** Flags a story's AI-written summary for review. */
@Composable
private fun ReportDialog(vm: AppViewModel, card: Card, date: String, onDismiss: () -> Unit) {
    val t = Mb.t
    val scope = rememberCoroutineScope()
    var reason by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = { if (!sending) onDismiss() },
        containerColor = t.bg,
        title = { Text("Report this summary", style = Type.title, color = t.ink) },
        text = {
            Column {
                Text("Summaries are written by AI and can get things wrong. What's the problem?",
                    style = Type.body, color = t.muted)
                Column(Modifier.padding(top = 12.dp)) {
                    REPORT_REASONS.forEach { (key, label) ->
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { reason = key }
                                .padding(vertical = 10.dp, horizontal = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            CheckDot(reason == key)
                            Spacer(Modifier.width(12.dp))
                            Text(label, style = Type.value, color = t.ink)
                        }
                    }
                }
                PillField(note, { note = it.take(1000) }, "Anything to add? (optional)", Modifier.padding(top = 8.dp).fillMaxWidth())
                error?.let { Hint(it, Modifier.padding(top = 8.dp), color = t.error) }
            }
        },
        confirmButton = {
            PillButton("Send", enabled = reason != null, busy = sending) {
                val why = reason ?: return@PillButton
                sending = true
                error = null
                scope.launch {
                    error = vm.report(card, date, why, note)
                    sending = false
                    if (error == null) {
                        vm.message.value = "Thanks. We'll take a look."
                        onDismiss()
                    }
                }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !sending) { Text("Cancel", color = t.ink) } },
    )
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
