package me.vattitude.morningbrief.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import me.vattitude.morningbrief.pipeline.FOLLOW_EXAMPLES
import me.vattitude.morningbrief.pipeline.SECTIONS
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
    val t = Mb.t

    LaunchedEffect(email) { vm.loadSources() }

    LazyColumn(modifier.fillMaxSize(), contentPadding = ScreenPadding) {
        item {
            ScreenHeader(
                overline = { Overline(if (email != null) "Synced with the web app" else "On this phone") },
                title = "Sources",
                subtitle = "What goes into tomorrow's brief.",
            )
        }
        note?.let { n -> item { Hint(n, Modifier.padding(top = 12.dp), color = t.error) } }
        if (busy && sources.isEmpty()) item {
            CircularProgressIndicator(Modifier.padding(top = 22.dp).size(24.dp), color = t.ink, strokeWidth = 2.dp)
        }

        item { Follow(vm, st.stories["follow"] ?: 0, sources.filter { it.section == "follow" }) { removing = it } }

        SECTIONS.values.filter { it.isCategory || it.key == "local" }.forEachIndexed { index, s ->
            item(key = "s:${s.key}") {
                val n = st.stories[s.key] ?: 0
                val city = st.newsCity.ifBlank { st.city }.substringBefore(",").trim()
                val label = if (s.key == "local" && city.isNotBlank()) "${s.title} · $city" else s.title
                SectionLabel(label, detail = if (index == 0) "Stories per brief. Set to 0 to skip." else null) {
                    PillStepper(n) { vm.setStories(s.key, it) }
                }
                if (n > 0) GlassGroup {
                    if (s.key == "local") LocalCity(vm, st.newsCity, st.city)
                    sources.filter { it.section == s.key }.forEachIndexed { i, src ->
                        if (i > 0 || s.key == "local") Hairline()
                        SourceRow(vm, src)
                    }
                }
            }
        }

        item { MyLinks(vm, st.stories["custom"] ?: 0, sources.filter { it.section == "custom" }) { removing = it } }
    }

    removing?.let { src ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(if (src.section == "follow") "Stop following ${src.name}?" else "Remove ${src.name}?", style = Type.title) },
            confirmButton = { TextButton(onClick = { vm.removeSource(src); removing = null }) { Text("Remove", color = t.error) } },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Cancel", color = t.ink) } },
        )
    }
}

private fun host(url: String) = runCatching { URI(url).host?.removePrefix("www.") }.getOrNull() ?: url

@Composable
private fun SourceRow(vm: AppViewModel, src: Source, onRemove: ((Source) -> Unit)? = null) {
    val t = Mb.t
    Row(
        Modifier.fillMaxWidth().clickable { vm.setEnabled(src, !src.enabled) }.padding(vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(src.name, style = if (src.section == "follow") Type.title else Type.body, color = t.ink,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            val detail = if (src.section == "follow") "From anywhere it's reported" else host(src.url) + when (src.kind) {
                "article" -> " · single article"
                "page" -> " · page of links"
                else -> ""
            }
            Text(detail, Modifier.padding(top = 3.dp), style = Type.tiny, color = t.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (onRemove != null && !src.builtin) {
            Icon(Icons.Outlined.Close, "Remove", Modifier.padding(end = 6.dp).size(36.dp).clip(CircleShape)
                .clickable { onRemove(src) }.padding(9.dp), tint = t.muted)
        }
        CheckDot(src.enabled)
    }
}

@Composable
private fun LocalCity(vm: AppViewModel, newsCity: String, weatherCity: String) {
    var picking by remember { mutableStateOf(false) }
    ListRow(
        "City",
        value = when {
            newsCity.isNotBlank() -> newsCity.substringBefore(",")
            weatherCity.isNotBlank() -> "${weatherCity.substringBefore(",")} (weather)"
            else -> "Not set"
        },
        caret = true,
        onClick = { picking = !picking },
    )
    if (picking) {
        Column(Modifier.padding(bottom = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            CitySearch(vm) { p ->
                vm.setNewsCity(if (p.region.isNotBlank()) "${p.name}, ${p.region}" else p.name)
                picking = false
            }
            if (newsCity.isNotBlank() && weatherCity.isNotBlank()) {
                Chip("Use the weather city (${weatherCity.substringBefore(",")})") { vm.setNewsCity(""); picking = false }
            }
        }
    }
}

/** A pill field with the round ink button beside it. */
@Composable
private fun AddField(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    icon: ImageVector,
    label: String,
    working: Boolean,
    workingText: String,
    error: String?,
    keyboard: KeyboardOptions,
    modifier: Modifier = Modifier,
    onGo: () -> Unit,
) {
    Column(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            PillField(value, onChange, placeholder, Modifier.weight(1f), icon = icon, error = error != null,
                keyboardOptions = keyboard, keyboardActions = KeyboardActions(onDone = { onGo() }, onGo = { onGo() }))
            Spacer(Modifier.width(8.dp))
            InkCircle(Icons.Outlined.Add, label, enabled = value.isNotBlank(), busy = working, onClick = onGo)
        }
        error?.let { Hint(it, Modifier.padding(top = 8.dp, start = 18.dp), color = Mb.t.error) }
        if (working) Hint(workingText, Modifier.padding(top = 8.dp, start = 18.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Follow(vm: AppViewModel, n: Int, followed: List<Source>, onRemove: (Source) -> Unit) {
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
    AddField(query, { query = it; error = null }, "A player, team, company…", Icons.Outlined.Search, "Follow",
        working, "Looking for news…", error, KeyboardOptions(imeAction = ImeAction.Done), Modifier.padding(top = 22.dp)) { go() }
    if (followed.isEmpty()) {
        FlowRow(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (ex in FOLLOW_EXAMPLES) Chip(ex) { query = ex; error = null }
        }
        return
    }
    SectionLabel("Following", detail = "Their news from wherever it's reported, in its own section.") {
        PillStepper(n) { vm.setStories("follow", it) }
    }
    GlassGroup {
        followed.forEachIndexed { i, src ->
            if (i > 0) Hairline()
            SourceRow(vm, src, onRemove)
        }
    }
    if (n == 0) Hint("Following is off, so these won't be in your briefing.", Modifier.padding(top = 8.dp, start = 4.dp),
        color = Mb.t.error)
}

@Composable
private fun MyLinks(vm: AppViewModel, n: Int, mine: List<Source>, onRemove: (Source) -> Unit) {
    val scope = rememberCoroutineScope()
    val shared by vm.sharedUrl.collectAsState()
    var url by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(shared) { shared?.let { url = it } }
    fun go() {
        if (url.isBlank() || adding) return
        adding = true
        scope.launch {
            error = vm.addSource(url, "custom")
            if (error == null) url = ""
            adding = false
        }
    }
    SectionLabel(SECTIONS.getValue("custom").title,
        detail = "Any link with news on it: a site, a feed, a team's page, an article. Or share one to this app.") {
        PillStepper(n) { vm.setStories("custom", it) }
    }
    AddField(url, { url = it; error = null }, "https://…", Icons.Outlined.Link, "Add link", adding, "Checking the link…", error,
        KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go)) { go() }
    if (mine.isEmpty()) {
        Row(Modifier.padding(top = 12.dp)) { Chip("Try: cbc.ca/sports/hockey/nhl") { url = LINK_EXAMPLE; error = null } }
        return
    }
    GlassGroup(Modifier.padding(top = 12.dp)) {
        mine.forEachIndexed { i, src ->
            if (i > 0) Hairline()
            SourceRow(vm, src, onRemove)
        }
    }
    if (n == 0) Hint("My Sources is off, so these won't be in your briefing.", Modifier.padding(top = 8.dp, start = 4.dp),
        color = Mb.t.error)
}
