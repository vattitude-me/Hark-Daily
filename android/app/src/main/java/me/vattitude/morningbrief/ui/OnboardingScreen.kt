package me.vattitude.morningbrief.ui

import android.Manifest
import android.app.TimePickerDialog
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material.icons.outlined.RecordVoiceOver
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import me.vattitude.morningbrief.R
import me.vattitude.morningbrief.pipeline.KOKORO_VOICES
import me.vattitude.morningbrief.pipeline.KokoroPack
import me.vattitude.morningbrief.pipeline.MAX_PER_SECTION
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.STORY_BUDGET
import me.vattitude.morningbrief.pipeline.kokoroVoice
import me.vattitude.morningbrief.work.Scheduler

private enum class Step { Welcome, Voice, Morning, Topics, Summaries, Ready }

/**
 * First run: hear what a briefing sounds like, then pick the voice, the morning time (and allow the
 * "it's ready" notification) and, optionally, who writes the summaries. Ends by making the first brief.
 */
@Composable
fun OnboardingScreen(vm: AppViewModel) {
    var index by rememberSaveable { mutableIntStateOf(0) }
    val step = Step.entries[index]
    val st by vm.settings.collectAsState()
    val context = LocalContext.current
    val t = Mb.t

    var canNotify by remember {
        mutableStateOf(Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)
    }
    var asked by rememberSaveable { mutableStateOf(false) }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        canNotify = granted
        asked = true
        if (step == Step.Morning) index++
    }

    BackHandler(index > 0) { index-- }
    LaunchedEffect(step) { if (step != Step.Welcome) vm.stopDemo() }

    Column(Modifier.fillMaxSize().backdrop(t).statusBarsPadding().navigationBarsPadding().imePadding()) {
        // Progress: one dash per step.
        Row(Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, top = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (i in Step.entries.indices) {
                Box(Modifier.weight(1f).height(3.dp).clip(CircleShape).background(if (i <= index) t.ink else t.track))
            }
        }
        AnimatedContent(step, Modifier.weight(1f), transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "step") { s ->
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 28.dp)) {
                when (s) {
                    Step.Welcome -> Welcome(vm)
                    Step.Voice -> VoiceStep(vm)
                    Step.Morning -> MorningStep(vm, canNotify) { askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) }
                    Step.Topics -> TopicsStep(vm)
                    Step.Summaries -> SummariesStep(vm)
                    Step.Ready -> ReadyStep(vm, canNotify)
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 24.dp, bottom = 16.dp, top = 8.dp),
            verticalAlignment = Alignment.CenterVertically) {
            if (index > 0) TextButton(onClick = { index-- }) { Text("Back", style = Type.value, color = t.muted) }
            Spacer(Modifier.weight(1f))
            val totalStories = SECTIONS.keys.sumOf { st.stories[it] ?: 0 }
            val topicsEmpty = step == Step.Topics && totalStories == 0
            val label = when (step) {
                Step.Welcome -> "Get started"
                Step.Topics -> if (topicsEmpty) "Pick at least one topic" else "Continue"
                Step.Summaries -> if (st.summaryKey.isBlank()) "Skip for now" else "Continue"
                Step.Ready -> "Make my first brief"
                else -> "Continue"
            }
            PillButton(label, filled = !(step == Step.Summaries && st.summaryKey.isBlank()), enabled = !topicsEmpty) {
                when {
                    step == Step.Morning && !canNotify && !asked -> askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                    step == Step.Ready -> vm.finishOnboarding()
                    else -> index++
                }
            }
        }
    }
}

@Composable
private fun Title(overline: String, title: String, lead: String) {
    Overline(overline)
    Text(title, Modifier.padding(top = 10.dp), style = Type.display, color = Mb.t.ink)
    Text(lead, Modifier.padding(top = 10.dp, bottom = 22.dp), style = Type.lead, color = Mb.t.muted)
}

/** The app icon, from its two adaptive layers. */
@Composable
private fun AppMark(size: Int = 84) {
    Box(Modifier.size(size.dp).clip(RoundedCornerShape((size * .28f).dp)), contentAlignment = Alignment.Center) {
        // The layers are 108dp with the visible icon in the middle 72dp.
        val full = (size * 108 / 72).dp
        Image(painterResource(R.drawable.ic_launcher_background), null, Modifier.requiredSize(full))
        Image(painterResource(R.drawable.ic_launcher_foreground), null, Modifier.requiredSize(full))
    }
}

@Composable
private fun Welcome(vm: AppViewModel) {
    val demo by vm.demo.collectAsState()
    val t = Mb.t
    AppMark()
    Spacer(Modifier.height(26.dp))
    Title("Morning Brief", "Your news, read aloud every morning.",
        "Five minutes of the stories you care about, waiting when you wake. Made on your phone, " +
            "with no ads and no account.")
    Glass(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            InkCircle(if (demo != null) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                if (demo != null) "Pause the sample" else "Play a sample brief", size = 52.dp) { vm.toggleDemo() }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("Hear how it sounds", style = Type.title, color = t.ink)
                Text("The start of a real brief, read by Heart", Modifier.padding(top = 2.dp),
                    style = Type.meta, color = t.muted)
                Box(Modifier.padding(top = 10.dp).fillMaxWidth().height(3.dp).clip(CircleShape).background(t.track)) {
                    Box(Modifier.fillMaxWidth(demo ?: 0f).fillMaxHeight().background(t.ink))
                }
            }
        }
    }
    Column(Modifier.padding(top = 22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Feature(Icons.Outlined.RecordVoiceOver, "Sounds like a real host", "Natural voices that run on your phone, even offline")
        Feature(Icons.Outlined.Schedule, "Ready before your alarm", "Made overnight, with one quiet alert when it's done")
        Feature(Icons.Outlined.AutoAwesome, "Only what you follow", "Topics, local news, people, teams or any site you like")
    }
}

@Composable
private fun Feature(icon: ImageVector, title: String, detail: String) {
    val t = Mb.t
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(38.dp).clip(CircleShape).background(t.glass), contentAlignment = Alignment.Center) {
            Icon(icon, null, Modifier.size(19.dp), tint = t.ink)
        }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(title, style = Type.title, color = t.ink)
            Text(detail, style = Type.meta, color = t.muted)
        }
    }
}

@Composable
private fun VoiceStep(vm: AppViewModel) {
    val st by vm.settings.collectAsState()
    val pack by vm.packInstalled.collectAsState()
    // Natural voices are the point of the app, so they're the starting choice.
    LaunchedEffect(Unit) {
        vm.loadVoices()
        if (st.voice == null && pack == null) vm.update { it.copy(voice = KOKORO_VOICES.first().id) }
    }
    Title("Step 1 of 4 · Voice", "Who should read your news?",
        "Natural voices sound like a real host and work offline once downloaded. " +
            "The phone's own voice works right away.")
    Glass(Modifier.fillMaxWidth()) { VoicePicker(vm, Modifier.padding(14.dp)) }
}

@Composable
private fun MorningStep(vm: AppViewModel, canNotify: Boolean, onAllow: () -> Unit) {
    val st by vm.settings.collectAsState()
    val context = LocalContext.current
    val t = Mb.t
    val time = LocalTime.of(st.readyHour, st.readyMinute)
    Title("Step 2 of 4 · Every morning", "When do you want your brief?",
        "Pick when you usually wake or head out. Your brief is ready by then, every day.")
    Glass(Modifier.fillMaxWidth().clickable {
        TimePickerDialog(context, { _, h, m -> vm.update { it.copy(readyBy = "%02d:%02d".format(h, m)) } },
            st.readyHour, st.readyMinute, false).show()
    }) {
        Column(Modifier.fillMaxWidth().padding(vertical = 22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Overline("Ready by")
            Text(time.format(DateTimeFormatter.ofPattern("h:mm", Locale.ENGLISH)), Modifier.padding(top = 6.dp),
                style = Type.display.copy(fontSize = 56.sp, lineHeight = 60.sp), color = t.ink)
            Text(time.format(DateTimeFormatter.ofPattern("a", Locale.ENGLISH)), style = Type.title, color = t.muted)
            Text("Tap to change", Modifier.padding(top = 10.dp), style = Type.meta, color = t.muted)
        }
    }
    Glass(Modifier.fillMaxWidth().padding(top = 14.dp)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(if (canNotify) Icons.Outlined.Notifications else Icons.Outlined.NotificationsOff, null,
                Modifier.size(22.dp), tint = t.ink)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(if (canNotify) "We'll let you know" else "Get a nudge when it's ready", style = Type.title, color = t.ink)
                Text(if (canNotify) "One quiet notification when your brief is ready. Tap it to listen."
                else "One quiet notification each morning, nothing else.", style = Type.meta, color = t.muted)
            }
            if (!canNotify) {
                Spacer(Modifier.width(10.dp))
                PillButton("Allow", onClick = onAllow)
            }
        }
    }
    Hint("The phone starts on it about ${Scheduler.LEAD_MINUTES} minutes before, as long as it's online.",
        Modifier.padding(top = 14.dp, start = 4.dp))
}

@Composable
private fun TopicsStep(vm: AppViewModel) {
    val st by vm.settings.collectAsState()
    val t = Mb.t
    val total = SECTIONS.keys.sumOf { st.stories[it] ?: 0 }
    val full = total >= STORY_BUDGET
    Title("Step 3 of 4 · Topics", "What goes in your brief?",
        "Twelve stories, split however you like — up to $MAX_PER_SECTION from each topic. Nothing is picked for you.")
    Glass(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.Bottom) {
                Text("$total of $STORY_BUDGET stories", Modifier.weight(1f), style = Type.title, color = t.ink)
            }
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                repeat(STORY_BUDGET) { i ->
                    Box(Modifier.weight(1f).height(6.dp).clip(CircleShape).background(if (i < total) t.ink else t.track))
                }
            }
            PillButton(if (total == 0) "Start with a balanced mix" else "Fill a balanced mix", filled = false,
                modifier = Modifier.padding(top = 14.dp), onClick = { vm.applyQuickMix() })
        }
    }
    GlassGroup(Modifier.padding(top = 12.dp)) {
        SECTIONS.values.filter { it.isCategory || it.key == "local" }.forEachIndexed { i, s ->
            if (i > 0) Hairline()
            val n = st.stories[s.key] ?: 0
            Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(32.dp).clip(CircleShape).background(t.glass), contentAlignment = Alignment.Center) {
                    Text(s.emoji, style = Type.body)
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(s.title, style = Type.body, color = t.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("Up to $MAX_PER_SECTION stories", Modifier.padding(top = 2.dp), style = Type.tiny, color = t.muted)
                }
                StoryStepper(n, canRaise = !full, max = MAX_PER_SECTION) { vm.setStories(s.key, it) }
            }
        }
    }
    if (total == 0) Hint("Pick at least one topic — or start with the balanced mix above.",
        Modifier.padding(top = 12.dp, start = 4.dp), color = t.error)
}

@Composable
private fun SummariesStep(vm: AppViewModel) {
    Title("Step 4 of 4 · Optional", "Want sharper summaries?",
        "Your brief already works without this: the app picks the key sentences from each article. " +
            "Add a free AI key and every story is rewritten to be heard, short and clear.")
    Glass(Modifier.fillMaxWidth()) { SummaryPicker(vm, Modifier.padding(14.dp)) }
    Hint("Takes about a minute. You can also skip it and add a key later in Settings, under Advanced.", Modifier.padding(top = 14.dp, start = 4.dp))
}

@Composable
private fun ReadyStep(vm: AppViewModel, canNotify: Boolean) {
    val st by vm.settings.collectAsState()
    val pack by vm.packInstalled.collectAsState()
    val download by vm.packDownload.collectAsState()
    val t = Mb.t
    Title("All set", "Your first brief is one tap away.", "Here's your setup. Change any of it later, and pick topics in Sources.")
    GlassGroup {
        val voice = kokoroVoice(st.voice)
        ListRow("Voice", value = when {
            voice == null -> "Phone"
            pack == null && download.running -> "${voice.name} (downloading)"
            pack == null -> "Phone (natural not downloaded)"
            else -> "${voice.name} · ${voice.accent}"
        })
        Hairline()
        ListRow("Ready by", value = LocalTime.of(st.readyHour, st.readyMinute).format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)) +
            if (canNotify) "" else ", no alert")
        Hairline()
        val total = SECTIONS.keys.sumOf { st.stories[it] ?: 0 }
        val topics = SECTIONS.values.filter { (st.stories[it.key] ?: 0) > 0 }.joinToString(", ") { it.title }
        ListRow("Topics", detail = topics.ifEmpty { "None yet" }, value = "$total stories")
        Hairline()
        ListRow("Summaries", value = if (st.summaryKey.isBlank()) "Built-in" else st.provider.name)
        Hairline()
        Row(Modifier.fillMaxWidth().padding(vertical = 15.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Your name", style = Type.body, color = t.ink)
            Spacer(Modifier.width(16.dp))
            BasicTextField(
                st.name, { v -> vm.update { it.copy(name = v.take(40)) } }, Modifier.weight(1f), singleLine = true,
                textStyle = Type.value.copy(color = t.ink, textAlign = TextAlign.End),
                cursorBrush = SolidColor(t.ink),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.CenterEnd) {
                        if (st.name.isEmpty()) Text("Optional, for the greeting", style = Type.value, color = t.muted)
                        inner()
                    }
                },
            )
        }
    }
    if (kokoroVoice(st.voice) != null && pack == null && !download.running) {
        Row(Modifier.padding(top = 14.dp, start = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Hint("The natural voices aren't downloaded yet.", Modifier.weight(1f))
            PillButton("Download", filled = false) { vm.downloadVoices(KokoroPack.HD) }
        }
    }
    Hint(if (kokoroVoice(st.voice) != null && pack == null && download.running)
        "Your first brief starts as soon as the natural voices finish downloading, then takes a few minutes."
    else "Your first brief takes a few minutes. After that, a new one is waiting every morning by " +
        LocalTime.of(st.readyHour, st.readyMinute).format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)) + ".",
        Modifier.padding(top = 14.dp, start = 4.dp), color = t.muted)
}
