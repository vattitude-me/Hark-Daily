package me.vattitude.morningbrief.ui

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Forward10
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import me.vattitude.morningbrief.pipeline.PHONE_VOICE

fun clock(seconds: Double): String {
    val s = seconds.toInt().coerceAtLeast(0)
    return "%d:%02d".format(s / 60, s % 60)
}

@OptIn(ExperimentalMaterial3Api::class)
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

    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.buildNow() }
    fun startBuild() {
        if (Build.VERSION.SDK_INT >= 33) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) else vm.buildNow()
    }

    val b = briefing
    val mine = player.date == b?.date
    val position = if (mine) player.position else 0.0
    val playing = mine && player.playing
    val voiceChanged = remember(b, saved, pack) { b != null && vm.voiceChanged(b, saved) }

    LazyColumn(modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Morning Brief", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(b?.title ?: "Your briefing", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            if (b != null) {
                val bits = listOfNotNull("${b.cards.size} stories", "${clock(b.duration)} long", b.weather)
                Text(bits.joinToString(" · "), style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (build.running) item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.padding(16.dp)) {
                    Text("Making your briefing", fontWeight = FontWeight.SemiBold)
                    Text(build.step, style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(progress = { build.fraction }, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(6.dp))
                    Text("This takes a few minutes. You can leave the app.", style = MaterialTheme.typography.bodySmall)
                }
            }
        } else build.error?.let { err ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Column(Modifier.padding(16.dp)) {
                        Text("The last briefing couldn't be made", fontWeight = FontWeight.SemiBold)
                        Text(err, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }

        if (b != null && !build.running && voiceChanged) item {
            val (id, name) = vm.currentVoice(saved)
            val now = if (id == PHONE_VOICE) "the phone voice" else name
            val then = if (b.voiceId.startsWith("kokoro:")) b.voiceName else "the phone voice"
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("You've switched to $now", fontWeight = FontWeight.SemiBold)
                    Text("This briefing was recorded with $then. Re-record it with the same stories, " +
                        "or the new voice starts with your next briefing.", style = MaterialTheme.typography.bodyMedium)
                    Button(onClick = { vm.revoice(b.date) }) { Text("Re-record with $now") }
                }
            }
        }

        if (b == null) {
            item {
                Card {
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Good morning!", style = MaterialTheme.typography.titleLarge)
                        Text("Morning Brief reads the news you choose and turns it into a short spoken briefing, " +
                            "made right here on your phone. Pick your sources and voice, or start with the defaults.")
                        Button(onClick = { startBuild() }, enabled = !build.running) { Text("Make my first briefing") }
                    }
                }
            }
            return@LazyColumn
        }

        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerHigh)) {
                Column(Modifier.padding(16.dp)) {
                    val now = b.chapters.lastOrNull { it.kind != "section" && position >= it.start }
                    Text(if (mine) now?.title ?: "Good morning" else "Ready to play",
                        style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    var dragging by remember { mutableStateOf<Float?>(null) }
                    Slider(
                        value = dragging ?: (position / b.duration.coerceAtLeast(1.0)).toFloat().coerceIn(0f, 1f),
                        onValueChange = { dragging = it },
                        onValueChangeFinished = {
                            dragging?.let { vm.seekTo(it * b.duration, play = playing) }
                            dragging = null
                        },
                    )
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(clock(position), style = MaterialTheme.typography.bodySmall)
                        Text(clock(b.duration), style = MaterialTheme.typography.bodySmall)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { vm.skip(-10) }) { Icon(Icons.Filled.Replay10, "Back 10 seconds") }
                        Spacer(Modifier.width(16.dp))
                        FilledIconButton(onClick = { vm.togglePlay() }, modifier = Modifier.size(64.dp), enabled = player.ready) {
                            Icon(if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                                if (playing) "Pause" else "Play", Modifier.size(36.dp))
                        }
                        Spacer(Modifier.width(16.dp))
                        IconButton(onClick = { vm.skip(10) }) { Icon(Icons.Filled.Forward10, "Forward 10 seconds") }
                    }
                }
            }
        }

        if (dates.size > 1) item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(dates) { d ->
                    FilterChip(selected = d == selected, onClick = { vm.select(d) }, label = { Text(dayLabel(d)) })
                }
            }
        }

        for (section in b.sections) {
            item(key = "s:${section.key}") {
                val lead = b.chapters.firstOrNull { it.id == "section:${section.key}" }
                Text("${section.emoji} ${section.title}".trim(), style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 8.dp).clickable(enabled = lead != null) { lead?.let { vm.seekTo(it.start) } })
            }
            items(b.cards.filter { it.section == section.key }, key = { "c:${it.id}" }) { card ->
                val current = mine && position >= card.start && position < card.end
                StoryCard(card, current,
                    onPlay = { vm.seekTo(card.start) },
                    onOpen = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(card.url))) })
            }
        }

        if (b.notes.isNotEmpty()) item {
            Column(Modifier.padding(top = 8.dp)) {
                for (n in b.notes) Text("• $n", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        item {
            OutlinedButton(onClick = { startBuild() }, enabled = !build.running, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                Icon(Icons.Outlined.Refresh, null)
                Spacer(Modifier.width(8.dp))
                Text(if (b.date == LocalDate.now().toString()) "Make a fresh briefing" else "Make today's briefing")
            }
        }
    }
}

@Composable
private fun StoryCard(card: Card, current: Boolean, onPlay: () -> Unit, onOpen: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Card(
        onClick = { open = !open },
        colors = CardDefaults.cardColors(
            containerColor = if (current) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainer,
        ),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(card.headline, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    val also = if (card.also.isEmpty()) "" else " +${card.also.size}"
                    Text("${card.source}$also · ${clock(card.start)}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (card.image != null) {
                    Spacer(Modifier.width(10.dp))
                    AsyncImage(model = card.image, contentDescription = null, contentScale = ContentScale.Crop,
                        modifier = Modifier.size(64.dp).clip(RoundedCornerShape(8.dp)))
                }
            }
            if (open) {
                Spacer(Modifier.height(8.dp))
                Text(card.summary, style = MaterialTheme.typography.bodyMedium)
                if (card.also.isNotEmpty()) {
                    Text("Also covered by ${card.also.joinToString(", ")}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.End) {
                Box(Modifier.weight(1f))
                IconButton(onClick = onPlay) { Icon(Icons.Filled.PlayArrow, "Play this story") }
                IconButton(onClick = onOpen) { Icon(Icons.AutoMirrored.Outlined.OpenInNew, "Open the article") }
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
