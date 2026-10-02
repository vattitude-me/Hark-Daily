package me.vattitude.morningbrief.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import me.vattitude.morningbrief.pipeline.FOLLOW_EXAMPLES
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.Section
import me.vattitude.morningbrief.pipeline.Source
import java.net.URI

/** A page of links the app can read without a feed, to show that any link works. */
private const val LINK_EXAMPLE = "https://www.cbc.ca/sports/hockey/nhl"

@Composable
fun SourcesScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val sources by vm.sources.collectAsState()
    val note by vm.sourcesNote.collectAsState()
    val busy by vm.sourcesBusy.collectAsState()
    val email by vm.signedInEmail.collectAsState()
    val st by vm.saved.collectAsState()
    var removing by remember { mutableStateOf<Source?>(null) }

    LaunchedEffect(email) { vm.loadSources() }

    LazyColumn(modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Sources", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            Text(
                if (email != null) "Synced with your account, so the web app shows the same choices."
                else "Kept on this phone. Sign in under Settings to share them with the web app.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        note?.let { n -> item { Text(n, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) } }
        if (busy && sources.isEmpty()) item { CircularProgressIndicator() }

        item { FollowCard(vm, st.stories["follow"] ?: 0, sources.filter { it.section == "follow" }) { removing = it } }

        item { Heading("Topics", "Set how many stories each gets in your briefing. Off skips it.") }
        for (s in SECTIONS.values.filter { it.isCategory || it.key == "local" }) {
            item(key = "s:${s.key}") {
                SectionCard(vm, s, st.stories[s.key] ?: 0, sources.filter { it.section == s.key }) {
                    if (s.key == "local") LocalCity(vm, st.newsCity, st.city)
                }
            }
        }

        item { Heading("Any link", "Anything with news on it: a site, a feed, a team's page, a single article.") }
        item { AddLinkCard(vm, st.stories["custom"] ?: 0, sources.filter { it.section == "custom" }) { removing = it } }
    }

    removing?.let { src ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(if (src.section == "follow") "Stop following ${src.name}?" else "Remove ${src.name}?") },
            confirmButton = { TextButton(onClick = { vm.removeSource(src); removing = null }) { Text("Remove") } },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun Heading(title: String, detail: String) {
    Column(Modifier.padding(top = 8.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Text(detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** "Off" or a count, with - and + buttons. */
@Composable
private fun Stepper(n: Int, onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { onChange(n - 1) }, enabled = n > 0) { Icon(Icons.Outlined.Remove, "Fewer stories") }
        Text(if (n == 0) "Off" else "$n", Modifier.width(32.dp), fontWeight = FontWeight.Medium, textAlign = TextAlign.Center)
        IconButton(onClick = { onChange(n + 1) }, enabled = n < 10) { Icon(Icons.Outlined.Add, "More stories") }
    }
}

@Composable
private fun SectionHeader(s: Section, n: Int, vm: AppViewModel) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("${s.emoji}  ${s.title}", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
        Stepper(n) { vm.setStories(s.key, it) }
    }
}

@Composable
private fun SourceRow(vm: AppViewModel, src: Source, onRemove: ((Source) -> Unit)? = null) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(src.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val detail = if (src.section == "follow") "news search" else {
                val host = runCatching { URI(src.url).host?.removePrefix("www.") }.getOrNull() ?: src.url
                host + when (src.kind) {
                    "article" -> " · single article"
                    "page" -> " · page of links"
                    else -> ""
                }
            }
            Text(detail, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (onRemove != null && !src.builtin) IconButton(onClick = { onRemove(src) }) { Icon(Icons.Outlined.Delete, "Remove") }
        Switch(checked = src.enabled, onCheckedChange = { vm.setEnabled(src, it) })
    }
}

/** A topic: its story count, and when it's on, its sources. */
@Composable
private fun SectionCard(vm: AppViewModel, s: Section, n: Int, list: List<Source>, extra: @Composable () -> Unit) {
    Card {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
            SectionHeader(s, n, vm)
            if (n > 0) {
                extra()
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                for (src in list) SourceRow(vm, src)
                if (list.isEmpty() && s.key == "local") Text("Pick a city to get local news.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun LocalCity(vm: AppViewModel, newsCity: String, weatherCity: String) {
    var picking by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("City for local news", style = MaterialTheme.typography.bodyMedium)
            Text(
                when {
                    newsCity.isNotBlank() -> newsCity
                    weatherCity.isNotBlank() -> "Same as weather ($weatherCity)"
                    else -> "Not set"
                },
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        TextButton(onClick = { picking = !picking }) { Text(if (picking) "Cancel" else "Change") }
    }
    if (picking) {
        if (newsCity.isNotBlank() && weatherCity.isNotBlank()) {
            TextButton(onClick = { vm.setNewsCity(""); picking = false }) { Text("Use the weather city ($weatherCity)") }
        }
        CitySearch(vm) { p ->
            vm.setNewsCity(if (p.region.isNotBlank()) "${p.name}, ${p.region}" else p.name)
            picking = false
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FollowCard(vm: AppViewModel, n: Int, followed: List<Source>, onRemove: (Source) -> Unit) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var working by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    fun go() {
        if (query.isBlank() || working) return
        working = true
        scope.launch {
            error = vm.follow(query)
            if (error == null) query = ""
            working = false
        }
    }
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SectionHeader(SECTIONS.getValue("follow"), n, vm)
            Text("A player, a team, a company or a topic. You get their news from wherever it's reported, in its own section.",
                style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                value = query, onValueChange = { query = it; error = null }, singleLine = true,
                placeholder = { Text("A name or topic") }, modifier = Modifier.fillMaxWidth(), isError = error != null,
                supportingText = error?.let { { Text(it) } },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            )
            if (followed.isEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (ex in FOLLOW_EXAMPLES) SuggestionChip(onClick = { query = ex; error = null }, label = { Text(ex) })
            }
            Button(enabled = query.isNotBlank() && !working, onClick = { go() }) {
                if (working) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Looking for news…")
                } else Text("Follow")
            }
            if (followed.isNotEmpty()) {
                HorizontalDivider()
                for (src in followed) SourceRow(vm, src, onRemove)
                if (n == 0) Text("Following is off, so these won't be in your briefing.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun AddLinkCard(vm: AppViewModel, n: Int, mine: List<Source>, onRemove: (Source) -> Unit) {
    val scope = rememberCoroutineScope()
    val shared by vm.sharedUrl.collectAsState()
    var url by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(shared) { shared?.let { url = it } }
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SectionHeader(SECTIONS.getValue("custom"), n, vm)
            Text("Paste a link, or share one to this app from your browser.", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                value = url, onValueChange = { url = it; error = null }, singleLine = true,
                placeholder = { Text("https://…") }, modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), isError = error != null,
                supportingText = error?.let { { Text(it) } },
            )
            if (mine.isEmpty()) SuggestionChip(onClick = { url = LINK_EXAMPLE; error = null },
                label = { Text("Try: cbc.ca/sports/hockey/nhl") })
            Button(
                enabled = url.isNotBlank() && !adding,
                onClick = {
                    adding = true
                    scope.launch {
                        error = vm.addSource(url, "custom")
                        if (error == null) url = ""
                        adding = false
                    }
                },
            ) {
                if (adding) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Checking the link…")
                } else Text("Add")
            }
            if (mine.isNotEmpty()) {
                HorizontalDivider()
                for (src in mine) SourceRow(vm, src, onRemove)
                if (n == 0) Text("My Sources is off, so these won't be in your briefing.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}
