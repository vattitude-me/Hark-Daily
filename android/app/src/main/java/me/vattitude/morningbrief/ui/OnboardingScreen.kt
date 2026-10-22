package me.vattitude.morningbrief.ui

import android.Manifest
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
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.FlashOn
import androidx.compose.material.icons.outlined.RecordVoiceOver
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import me.vattitude.morningbrief.R
import me.vattitude.morningbrief.pipeline.MAX_PER_SECTION
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.briefMinutes

private enum class Step { Welcome, Topics }

/**
 * First run onboarding flow for Hark Daily.
 * Features brand iconography, C-3PO audio sample preview, and customized topic curation.
 */
@Composable
fun OnboardingScreen(vm: AppViewModel) {
    var index by rememberSaveable { mutableIntStateOf(0) }
    val step = Step.entries[index]
    val st by vm.settings.collectAsState()
    val message by vm.message.collectAsState()
    val context = LocalContext.current
    val t = Mb.t
    val snackbar = remember { SnackbarHostState() }

    var canNotify by remember {
        mutableStateOf(
            Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        )
    }
    var asked by rememberSaveable { mutableStateOf(false) }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        canNotify = granted
        asked = true
        if (step == Step.Topics) vm.finishOnboarding()
    }

    BackHandler(index > 0) { index-- }
    LaunchedEffect(step) { if (step != Step.Welcome) vm.stopDemo() }
    LaunchedEffect(message) {
        message?.let {
            snackbar.showSnackbar(it)
            vm.message.value = null
        }
    }

    DisposableEffect(Unit) {
        onDispose { vm.stopDemo() }
    }

    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .backdrop(t)
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding()
        ) {
            // Progress dashes with amber active state
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 24.dp, end = 24.dp, top = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                for (i in Step.entries.indices) {
                    Box(
                        Modifier
                            .weight(1f)
                            .height(4.dp)
                            .clip(CircleShape)
                            .background(if (i <= index) t.accent else t.track)
                    )
                }
            }

            AnimatedContent(
                step,
                Modifier.weight(1f),
                transitionSpec = { fadeIn() togetherWith fadeOut() },
                label = "step"
            ) { s ->
                Column(
                    Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 24.dp, vertical = 24.dp)
                ) {
                    when (s) {
                        Step.Welcome -> Welcome(vm)
                        Step.Topics -> TopicsStep(vm)
                    }
                }
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 16.dp, end = 24.dp, bottom = 16.dp, top = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (index > 0) {
                    TextButton(onClick = {
                        vm.stopDemo()
                        index--
                    }) {
                        Text("Back", style = Type.value, color = t.muted)
                    }
                }
                Spacer(Modifier.weight(1f))
                val totalStories = SECTIONS.keys.sumOf { st.stories[it] ?: 0 }
                val topicsEmpty = step == Step.Topics && totalStories == 0

                val label = when (step) {
                    Step.Welcome -> "Get started"
                    Step.Topics -> if (topicsEmpty) "Pick at least one topic" else "Start listening"
                }
                PillButton(label, enabled = !topicsEmpty) {
                    vm.stopDemo()
                    when {
                        step == Step.Topics && !canNotify && !asked -> askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                        step == Step.Topics -> vm.finishOnboarding()
                        else -> index++
                    }
                }
            }
        }
        SnackbarHost(
            snackbar,
            Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 72.dp)
        )
    }
}

@Composable
private fun Title(overline: String, title: String, lead: String) {
    Overline(overline, color = Mb.t.accentText)
    Text(
        title,
        Modifier.padding(top = 8.dp),
        style = Type.display.copy(fontSize = 28.sp, lineHeight = 33.sp, fontWeight = FontWeight.Bold),
        color = Mb.t.ink
    )
    Text(
        lead,
        Modifier.padding(top = 8.dp, bottom = 20.dp),
        style = Type.lead.copy(fontSize = 14.5.sp, lineHeight = 21.sp),
        color = Mb.t.muted
    )
}

/** The official Hark Daily icon with amber ambient warmth. */
@Composable
private fun AppMark(size: Int = 80) {
    Box(
        Modifier
            .size(size.dp)
            .shadow(
                elevation = 16.dp,
                shape = RoundedCornerShape((size * .24f).dp),
                ambientColor = Color(0xFFF59E0B).copy(alpha = 0.35f),
                spotColor = Color(0xFFF59E0B).copy(alpha = 0.5f)
            )
            .clip(RoundedCornerShape((size * .24f).dp))
            .background(Color(0xFF0B1019)),
        contentAlignment = Alignment.Center
    ) {
        Image(
            painter = painterResource(R.drawable.ic_hark_logo),
            contentDescription = "Hark Daily",
            modifier = Modifier.fillMaxSize()
        )
    }
}

@Composable
private fun Welcome(vm: AppViewModel) {
    val demo by vm.demo.collectAsState()
    val t = Mb.t

    AppMark()
    Spacer(Modifier.height(20.dp))
    Title(
        "Hark Daily",
        "The news you hear, not just read.",
        "Five minutes of the stories you care about, recorded before you wake. No ads, no scrolling, pure audio."
    )

    // Audio preview deck
    Glass(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            JewelPlayButton(
                icon = if (demo != null) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                label = if (demo != null) "Pause sample" else "Play sample",
                size = 46.dp
            ) { vm.toggleDemo() }

            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("Hear how it sounds", style = Type.title.copy(fontWeight = FontWeight.Bold), color = t.ink)
                Text(
                    "Today's brief, narrated by C-3PO",
                    Modifier.padding(top = 2.dp),
                    style = Type.meta,
                    color = t.muted
                )
                Box(
                    Modifier
                        .padding(top = 8.dp)
                        .fillMaxWidth()
                        .height(3.dp)
                        .clip(CircleShape)
                        .background(t.track)
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(demo ?: 0f)
                            .fillMaxHeight()
                            .background(t.accent)
                    )
                }
            }
        }
    }

    Column(Modifier.padding(top = 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Feature(Icons.Outlined.SmartToy, "Voiced by C-3PO & more", "Your daily news delivered with protocol precision, or choose Alice, Mike, and Jerry")
        Feature(Icons.Outlined.Schedule, "Ready before your alarm", "A new brief appears each morning. Nothing to build or wait for")
        Feature(Icons.Outlined.AutoAwesome, "Only your topics", "Pick your sections, and how many stories each gets")
    }
}

@Composable
private fun Feature(icon: ImageVector, title: String, detail: String) {
    val t = Mb.t
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(38.dp)
                .clip(CircleShape)
                .background(t.accentSoft)
                .border(1.dp, t.accentLine, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Icon(icon, null, Modifier.size(19.dp), tint = t.accentText)
        }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(title, style = Type.title.copy(fontSize = 14.5.sp, fontWeight = FontWeight.SemiBold), color = t.ink)
            Text(detail, style = Type.meta, color = t.muted)
        }
    }
}

@Composable
private fun TopicsStep(vm: AppViewModel) {
    val st by vm.settings.collectAsState()
    val t = Mb.t
    val total = SECTIONS.keys.sumOf { st.stories[it] ?: 0 }

    Title(
        "Your topics",
        "What goes in your brief?",
        "Up to $MAX_PER_SECTION stories from each topic, however you like it. Nothing is picked for you."
    )

    Glass(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(
                if (total == 0) "Nothing picked yet" else "$total stories, about ${briefMinutes(total)} min",
                style = Type.title.copy(fontWeight = FontWeight.Bold),
                color = t.ink,
            )
            PillButton(
                if (total == 0) "Start with a balanced mix" else "Fill a balanced mix",
                filled = false,
                modifier = Modifier.padding(top = 12.dp),
                onClick = { vm.applyQuickMix() }
            )
        }
    }

    GlassGroup(Modifier.padding(top = 12.dp)) {
        SECTIONS.values.filter { it.isCategory || it.key == "local" }.forEachIndexed { i, s ->
            if (i > 0) Hairline()
            val n = st.stories[s.key] ?: 0
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    Modifier
                        .size(6.dp)
                        .clip(CircleShape)
                        .background(t.categoryColor(s.key))
                )
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(s.title, style = Type.body.copy(fontWeight = FontWeight.Medium), color = t.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("Up to $MAX_PER_SECTION stories", Modifier.padding(top = 2.dp), style = Type.tiny, color = t.muted)
                }
                StoryStepper(n, canRaise = true, max = MAX_PER_SECTION) { vm.setStories(s.key, it) }
            }
        }
    }

    if (total == 0) {
        Hint(
            "Pick at least one topic, or start with the balanced mix above.",
            Modifier.padding(top = 12.dp, start = 4.dp),
            color = t.error
        )
    }
}
