package me.vattitude.morningbrief.ui

import android.Manifest
import android.app.TimePickerDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Article
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Face
import androidx.compose.material.icons.outlined.RecordVoiceOver
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import me.vattitude.morningbrief.R
import me.vattitude.morningbrief.BuildConfig
import me.vattitude.morningbrief.pipeline.KOKORO_VOICES
import me.vattitude.morningbrief.pipeline.PHONE_VOICE
import me.vattitude.morningbrief.pipeline.Place
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.kokoroVoice
import me.vattitude.morningbrief.work.Scheduler
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
private fun Section(icon: ImageVector, title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(10.dp))
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            }
            content()
        }
    }
}

@Composable
private fun Hint(text: String) =
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

@Composable
private fun SwitchRow(label: String, checked: Boolean, detail: String? = null, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onChange(!checked) }, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label)
            detail?.let { Hint(it) }
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

/** A label with its value on the right, for things changed in a dialog or an expanding panel. */
@Composable
private fun ValueRow(label: String, value: String, enabled: Boolean = true, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(enabled = enabled, onClick = onClick).padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f))
        Text(value, color = if (enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.Medium)
    }
}

/** A one-line warning with its fix, e.g. notifications switched off. */
@Composable
private fun Nudge(text: String, action: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Outlined.WarningAmber, null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(text, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = onClick) { Text(action) }
    }
}

@Composable
fun SettingsScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val st by vm.settings.collectAsState()
    val saved by vm.saved.collectAsState()
    val dirty = st != saved
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current

    // Permissions can change in the system screens we send people to, so re-check on resume.
    var resumed by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            resumed++
            vm.loadVoices()
        }
    }
    val pm = context.getSystemService(PowerManager::class.java)
    val unrestricted = remember(resumed) { pm.isIgnoringBatteryOptimizations(context.packageName) }
    val canNotify = remember(resumed) {
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { resumed++ }

    Box(modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Settings", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)

            Section(Icons.Outlined.WbSunny, "Every morning") {
                SwitchRow("Make a briefing every day", st.daily) { on -> vm.update { it.copy(daily = on) } }
                val ready = LocalTime.of(st.readyHour, st.readyMinute)
                val fmt = DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)
                ValueRow("Ready by", ready.format(fmt), enabled = st.daily) {
                    TimePickerDialog(context, { _, h, m -> vm.update { it.copy(readyBy = "%02d:%02d".format(h, m)) } },
                        st.readyHour, st.readyMinute, false).show()
                }
                if (st.daily) Hint("It starts about ${Scheduler.LEAD_MINUTES} minutes earlier, whenever the phone is online.")
                if (!canNotify) Nudge("Notifications are off", "Allow") {
                    askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
                if (!unrestricted) Nudge("The phone may pause the morning build", "Fix") {
                    runCatching {
                        context.startActivity(Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:${context.packageName}")))
                    }
                }
            }

            VoiceSection(vm)

            Section(Icons.AutoMirrored.Outlined.Article, "Stories") {
                for (s in SECTIONS.values) {
                    val n = st.stories[s.key] ?: 0
                    fun set(v: Int) = vm.update { it.copy(stories = it.stories + (s.key to v.coerceIn(0, 10))) }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("${s.emoji}  ${s.title}", Modifier.weight(1f))
                        IconButton(onClick = { set(n - 1) }, enabled = n > 0) { Icon(Icons.Outlined.Remove, "Fewer") }
                        Text(if (n == 0) "Off" else "$n", Modifier.width(32.dp), fontWeight = FontWeight.Medium,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                        IconButton(onClick = { set(n + 1) }, enabled = n < 10) { Icon(Icons.Outlined.Add, "More") }
                    }
                }
                SwitchRow("Say where each story is from", st.saySources) { on -> vm.update { it.copy(saySources = on) } }
            }

            Section(Icons.Outlined.Face, "Greeting and weather") {
                OutlinedTextField(st.name, { v -> vm.update { it.copy(name = v.take(40)) } },
                    label = { Text("Your name") }, placeholder = { Text("Used in the greeting") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                SwitchRow("Start with the weather", st.weather) { on -> vm.update { it.copy(weather = on) } }
                if (st.weather) {
                    var picking by remember { mutableStateOf(false) }
                    ValueRow("City", st.city) { picking = !picking }
                    if (picking) CitySearch(vm) { p ->
                        vm.update { it.copy(city = p.name, latitude = p.latitude, longitude = p.longitude) }
                        picking = false
                    }
                }
            }

            AccountSection(vm)

            Section(Icons.Outlined.Tune, "Advanced") {
                var open by remember { mutableStateOf(st.groqKey.isNotBlank()) }
                Row(Modifier.fillMaxWidth().clickable { open = !open }, verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("AI-written summaries")
                        Hint(if (st.groqKey.isBlank()) "Off: summaries are made on the phone" else "On, with your Groq key")
                    }
                    Icon(if (open) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null)
                }
                if (open) {
                    Hint("Paste a free key from console.groq.com. It stays on this phone.")
                    OutlinedTextField(st.groqKey, { v -> vm.update { it.copy(groqKey = v.trim()) } },
                        label = { Text("Groq API key") }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                }
            }

            Text("Morning Brief ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            // Room for the save bar.
            Spacer(Modifier.height(if (dirty) 72.dp else 8.dp))
        }

        if (dirty) {
            Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth(), tonalElevation = 6.dp, shadowElevation = 6.dp) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Unsaved changes", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = { vm.discard() }) { Text("Discard") }
                    Spacer(Modifier.width(8.dp))
                    Button(onClick = { vm.save() }) { Text("Save") }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun VoiceSection(vm: AppViewModel) {
    val st by vm.settings.collectAsState()
    val installed by vm.packInstalled.collectAsState()
    val download by vm.packDownload.collectAsState()
    val phoneVoices by vm.voices.collectAsState()
    val previewing by vm.previewing.collectAsState()
    val natural = kokoroVoice(st.voice) != null || (st.voice == null && installed)
    var lastKokoro by remember { mutableStateOf(kokoroVoice(st.voice)?.id ?: KOKORO_VOICES.first().id) }
    var confirmRemove by remember { mutableStateOf(false) }

    Section(Icons.Outlined.RecordVoiceOver, "Voice") {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SegmentedButton(selected = natural, onClick = { vm.update { it.copy(voice = lastKokoro) } },
                shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text("Natural") }
            SegmentedButton(selected = !natural, onClick = { vm.update { it.copy(voice = PHONE_VOICE) } },
                shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text("Phone") }
        }

        if (natural) {
            when {
                download.running -> {
                    Text("Downloading natural voices… ${(download.fraction * 100).toInt()}%")
                    LinearProgressIndicator(progress = { download.fraction }, modifier = Modifier.fillMaxWidth())
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Hint("You can leave this screen; it keeps going.")
                        Spacer(Modifier.weight(1f))
                        TextButton(onClick = { vm.cancelDownload() }) { Text("Cancel") }
                    }
                }
                !installed -> {
                    Hint("Lifelike Kokoro voices, the same ones as the web app. A one-time 130 MB download " +
                        "(Wi-Fi recommended); after that they work offline.")
                    download.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    Button(onClick = { vm.downloadVoices() }) { Text("Download natural voices") }
                }
                else -> {
                    val current = kokoroVoice(st.voice) ?: KOKORO_VOICES.first()
                    VoicePicker(
                        options = KOKORO_VOICES.map { it.id to "${it.name} · ${it.accent}" },
                        details = KOKORO_VOICES.associate { it.id to it.description },
                        selected = current.id,
                        loading = previewing == current.id,
                        onSelect = { id -> lastKokoro = id; vm.update { it.copy(voice = id) }; vm.previewVoice(id) },
                        onPlay = { vm.previewVoice(current.id) },
                    )
                    if (confirmRemove) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Hint("Remove the voices? Briefings will use the phone's voice.")
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { confirmRemove = false }) { Text("Keep") }
                            TextButton(onClick = { confirmRemove = false; vm.removeVoices() }) { Text("Remove") }
                        }
                    } else {
                        val mb = remember(installed) { vm.packSize() / 1_000_000 }
                        TextButton(onClick = { confirmRemove = true }, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                            Text("Remove download ($mb MB)", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        } else {
            val options = listOf(PHONE_VOICE to "Automatic") + phoneVoices.map { it.name to it.label }
            val selected = st.voice?.takeIf { v -> options.any { it.first == v } } ?: PHONE_VOICE
            VoicePicker(
                options = options,
                details = emptyMap(),
                selected = selected,
                loading = false,
                onSelect = { id -> vm.update { it.copy(voice = id) }; vm.previewVoice(id) },
                onPlay = { vm.previewVoice(selected) },
            )
            Hint("Your phone's built-in voice: no download, but flatter than the natural voices.")
        }

        HorizontalDivider()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Speed", Modifier.weight(1f))
            Text("${"%.2f".format(st.speed)}×", fontWeight = FontWeight.Medium)
        }
        Slider(value = st.speed, valueRange = 0.8f..1.3f, steps = 9,
            onValueChange = { v -> vm.update { it.copy(speed = (v * 20).toInt() / 20f) } })
    }
}

/** A dropdown of voices with a play button beside it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun VoicePicker(
    options: List<Pair<String, String>>,
    details: Map<String, String>,
    selected: String,
    loading: Boolean,
    onSelect: (String) -> Unit,
    onPlay: () -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }, modifier = Modifier.weight(1f)) {
            OutlinedTextField(
                value = options.firstOrNull { it.first == selected }?.second ?: "",
                onValueChange = {},
                readOnly = true,
                singleLine = true,
                label = { Text("Voice") },
                supportingText = details[selected]?.let { { Text(it) } },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = open) },
                modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
            )
            ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                for ((id, label) in options) {
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(label)
                                details[id]?.let { Hint(it) }
                            }
                        },
                        onClick = { open = false; onSelect(id) },
                    )
                }
            }
        }
        Spacer(Modifier.width(8.dp))
        FilledTonalIconButton(onClick = onPlay, enabled = !loading) {
            if (loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(Icons.Filled.PlayArrow, "Play a sample")
        }
    }
}

@Composable
private fun AccountSection(vm: AppViewModel) {
    val email by vm.signedInEmail.collectAsState()
    val signIn by vm.signIn.collectAsState()
    Section(Icons.Outlined.AccountCircle, "Account") {
        if (email != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(email!!)
                    Hint("Sources and settings sync with the web app")
                }
                OutlinedButton(onClick = { vm.signOut() }) { Text("Sign out") }
            }
            return@Section
        }
        Text("Not signed in")
        Hint("Optional: sign in with the Google account you use on the web app to sync sources and settings")
        signIn.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        val context = LocalContext.current
        OutlinedButton(onClick = {
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, vm.googleSignInUrl())
        }, enabled = !signIn.busy) {
            if (signIn.busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
            else Icon(painterResource(R.drawable.ic_google), null, Modifier.size(18.dp), tint = Color.Unspecified)
            Spacer(Modifier.width(8.dp))
            Text("Continue with Google")
        }
    }
}

@Composable
private fun CitySearch(vm: AppViewModel, onPick: (Place) -> Unit) {
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Place>>(emptyList()) }
    LaunchedEffect(query) {
        if (query.trim().length < 2) {
            results = emptyList()
            return@LaunchedEffect
        }
        delay(350)
        results = vm.places(query.trim())
    }
    OutlinedTextField(query, { query = it }, label = { Text("Search for a city") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    for (p in results.take(5)) {
        Text("${p.name}${if (p.region.isNotBlank()) ", ${p.region}" else ""}",
            Modifier.fillMaxWidth().clickable { onPick(p); query = ""; results = emptyList() }.padding(vertical = 8.dp))
    }
}
