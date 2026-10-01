package me.vattitude.morningbrief.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.Source
import java.net.URI

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SourcesScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val sources by vm.sources.collectAsState()
    val note by vm.sourcesNote.collectAsState()
    val busy by vm.sourcesBusy.collectAsState()
    val shared by vm.sharedUrl.collectAsState()
    val email by vm.signedInEmail.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(email) { vm.loadSources() }

    var url by remember { mutableStateOf("") }
    var section by remember { mutableStateOf("custom") }
    var adding by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var removing by remember { mutableStateOf<Source?>(null) }
    LaunchedEffect(shared) { shared?.let { url = it } }

    LazyColumn(modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Text("Sources", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            Text(
                if (email != null) "Synced with your account, so the web app shows the same list."
                else "Kept on this phone. Sign in under Settings to share them with the web app.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Add a link", style = MaterialTheme.typography.titleMedium)
                    Text("A news site, a feed, a page of links or a single article. You can also share a link to this app " +
                        "from your browser.", style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(
                        value = url, onValueChange = { url = it; error = null }, singleLine = true,
                        placeholder = { Text("https://…") }, modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), isError = error != null,
                        supportingText = error?.let { { Text(it) } },
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (s in SECTIONS.values) {
                            FilterChip(selected = section == s.key, onClick = { section = s.key }, label = { Text(s.title) })
                        }
                    }
                    Button(
                        enabled = url.isNotBlank() && !adding,
                        onClick = {
                            adding = true
                            scope.launch {
                                error = vm.addSource(url, section)
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
                }
            }
        }
        note?.let { n -> item { Text(n, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) } }
        if (busy && sources.isEmpty()) item { CircularProgressIndicator() }

        for (s in SECTIONS.values) {
            val list = sources.filter { it.section == s.key }
            if (list.isEmpty()) continue
            item(key = "h:${s.key}") {
                Text("${s.emoji} ${s.title}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 12.dp))
            }
            items(list, key = { "${it.id}:${it.url}" }) { src ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(src.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val host = runCatching { URI(src.url).host?.removePrefix("www.") }.getOrNull() ?: src.url
                        val kind = when (src.kind) {
                            "article" -> " · single article"
                            "page" -> " · page of links"
                            else -> ""
                        }
                        Text(host + kind, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    if (!src.builtin) IconButton(onClick = { removing = src }) { Icon(Icons.Outlined.Delete, "Remove") }
                    Switch(checked = src.enabled, onCheckedChange = { vm.setEnabled(src, it) })
                }
            }
        }
    }

    removing?.let { src ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text("Remove ${src.name}?") },
            confirmButton = { TextButton(onClick = { vm.removeSource(src); removing = null }) { Text("Remove") } },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Cancel") } },
        )
    }
}
