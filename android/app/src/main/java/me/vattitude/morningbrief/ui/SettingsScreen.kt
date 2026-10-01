package me.vattitude.morningbrief.ui

import android.Manifest
import android.app.TimePickerDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import me.vattitude.morningbrief.BuildConfig
import me.vattitude.morningbrief.pipeline.Place
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.work.Scheduler
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, detail: String? = null, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onChange(!checked) }, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label)
            detail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
fun SettingsScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val st by vm.settings.collectAsState()
    val email by vm.signedInEmail.collectAsState()
    val signIn by vm.signIn.collectAsState()
    val voices by vm.voices.collectAsState()
    val engine by vm.voiceEngine.collectAsState()
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

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)

        Section("Account") {
            if (email != null) {
                Text("Signed in as $email. Your sources and main settings match the web app.")
                OutlinedButton(onClick = { vm.signOut() }) { Text("Sign out") }
            } else if (!signIn.codeSent) {
                Text("Optional. Sign in with the email you use on the web app to share your sources and settings. " +
                    "Briefings are always made on this phone.", style = MaterialTheme.typography.bodySmall)
                var input by remember { mutableStateOf(signIn.email) }
                OutlinedTextField(input, { input = it }, label = { Text("Email") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), modifier = Modifier.fillMaxWidth())
                signIn.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                Button(onClick = { vm.sendCode(input) }, enabled = "@" in input && !signIn.busy) { Text("Email me a code") }
            } else {
                Text("We sent a code to ${signIn.email}. Enter it here.")
                var code by remember { mutableStateOf("") }
                OutlinedTextField(code, { code = it.filter(Char::isDigit).take(10) }, label = { Text("Code") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), modifier = Modifier.fillMaxWidth())
                signIn.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { vm.verify(code) }, enabled = code.length >= 6 && !signIn.busy) { Text("Sign in") }
                    TextButton(onClick = { vm.cancelSignIn() }) { Text("Use another email") }
                }
            }
        }

        Section("You") {
            var name by remember(st.name) { mutableStateOf(st.name) }
            OutlinedTextField(name, { name = it.take(40); vm.update { s -> s.copy(name = name) } },
                label = { Text("Your name (for the greeting)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        }

        Section("Every morning") {
            SwitchRow("Make a briefing every day", st.daily) { on -> vm.update { it.copy(daily = on) } }
            val ready = LocalTime.of(st.readyHour, st.readyMinute)
            val fmt = DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Ready by ${ready.format(fmt)}")
                    Text("Starts around ${ready.minusMinutes(Scheduler.LEAD_MINUTES).format(fmt)}, when the phone is online.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(enabled = st.daily, onClick = {
                    TimePickerDialog(context, { _, h, m -> vm.update { it.copy(readyBy = "%02d:%02d".format(h, m)) } },
                        st.readyHour, st.readyMinute, false).show()
                }) { Text("Change") }
            }
            if (!canNotify) {
                Text("Allow notifications to hear when your briefing is ready.", style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = { askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) }) { Text("Allow notifications") }
            }
            if (!unrestricted) {
                Text("Some phones stop apps working in the background. Letting Morning Brief run unrestricted keeps the " +
                    "morning briefing on time.", style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = {
                    runCatching {
                        context.startActivity(Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:${context.packageName}")))
                    }
                }) { Text("Allow background work") }
            }
        }

        Section("Stories") {
            for (s in SECTIONS.values) {
                val n = st.stories[s.key] ?: 0
                Text("${s.emoji} ${s.title}: ${if (n == 0) "off" else "$n stories"}")
                Slider(value = n.toFloat(), valueRange = 0f..10f, steps = 9,
                    onValueChange = { v -> vm.update { it.copy(stories = it.stories + (s.key to v.toInt())) } })
            }
            SwitchRow("Say where each story is from", st.saySources) { on -> vm.update { it.copy(saySources = on) } }
        }

        Section("Weather") {
            SwitchRow("Start with the weather", st.weather, detail = st.city) { on -> vm.update { it.copy(weather = on) } }
            if (st.weather) CitySearch(vm) { p ->
                vm.update { it.copy(city = p.name, latitude = p.latitude, longitude = p.longitude) }
            }
        }

        Section("Voice") {
            Text("Voices come from your phone's text-to-speech engine and work offline." +
                if (engine.isNotEmpty() && engine != "com.google.android.tts") " For the best voices, install Speech Services by Google." else "",
                style = MaterialTheme.typography.bodySmall)
            val ready = voices.filter { !it.needsDownload }
            if (ready.isEmpty()) Text("Loading voices…", style = MaterialTheme.typography.bodySmall)
            for (v in ready.take(12)) {
                Row(Modifier.fillMaxWidth().clickable { vm.update { it.copy(voice = v.name) }; vm.previewVoice(v.name) },
                    verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = st.voice == v.name || (st.voice == null && v == ready.first()),
                        onClick = { vm.update { it.copy(voice = v.name) }; vm.previewVoice(v.name) })
                    Text(v.label, Modifier.weight(1f))
                }
            }
            val more = voices.count { it.needsDownload }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    runCatching { context.startActivity(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA)) }
                }) { Text(if (more > 0) "Get $more more voices" else "Get more voices") }
                TextButton(onClick = { vm.previewVoice(st.voice) }) { Text("Play sample") }
            }
            HorizontalDivider()
            Text("Speed: ${"%.2f".format(st.speed)}×")
            Slider(value = st.speed, valueRange = 0.8f..1.3f, steps = 9,
                onValueChange = { v -> vm.update { it.copy(speed = (v * 20).toInt() / 20f) } })
        }

        Section("Better summaries (optional)") {
            Text("Without a key, summaries are made on the phone. A free Groq key (console.groq.com) lets an AI " +
                "write them instead. The key stays on this phone.", style = MaterialTheme.typography.bodySmall)
            var key by remember(st.groqKey) { mutableStateOf(st.groqKey) }
            OutlinedTextField(key, { key = it.trim(); vm.update { s -> s.copy(groqKey = key) } },
                label = { Text("Groq API key") }, singleLine = true, visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth())
        }

        Text("Morning Brief ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 16.dp))
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
    OutlinedTextField(query, { query = it }, label = { Text("Change city") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    for (p in results.take(5)) {
        Text("${p.name}${if (p.region.isNotBlank()) ", ${p.region}" else ""}",
            Modifier.fillMaxWidth().clickable { onPick(p); query = ""; results = emptyList() }.padding(vertical = 8.dp))
    }
}
