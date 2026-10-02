package me.vattitude.morningbrief.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Headphones
import androidx.compose.material.icons.outlined.RssFeed
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** Room each screen leaves above and below its content: the status bar, and the floating tab bar. */
val ScreenPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 24.dp, bottom = 120.dp)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Root(vm: AppViewModel) {
    val tab by vm.tab.collectAsState()
    val message by vm.message.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(message) {
        message?.let {
            snackbar.showSnackbar(it)
            vm.message.value = null
        }
    }
    val t = Mb.t
    Box(Modifier.fillMaxSize().backdrop(t)) {
        val m = Modifier.fillMaxSize().statusBarsPadding()
        when (tab) {
            Tab.Today -> TodayScreen(vm, m)
            Tab.Sources -> SourcesScreen(vm, m)
            Tab.Settings -> SettingsScreen(vm, m)
        }
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().imePadding()
            .padding(start = 20.dp, end = 20.dp, bottom = 16.dp)) {
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 76.dp)) {
                Snackbar(it, containerColor = t.ink, contentColor = t.onInk, shape = CircleShape)
            }
            if (!WindowInsets.isImeVisible) TabBar(tab) { vm.tab.value = it }
        }
    }
}

@Composable
private fun TabBar(tab: Tab, onSelect: (Tab) -> Unit) {
    val t = Mb.t
    val bar = if (t.dark) Color(0xFF1E1E1C) else Color(0xFFF4F4F1)
    Row(
        Modifier.fillMaxWidth().height(64.dp)
            .shadow(18.dp, CircleShape, ambientColor = Color.Black.copy(alpha = .2f), spotColor = Color.Black.copy(alpha = .2f))
            .clip(CircleShape).background(bar).border(1.dp, t.glassLine, CircleShape)
            .padding(6.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        for ((item, icon) in listOf(
            Tab.Today to Icons.Outlined.Headphones,
            Tab.Sources to Icons.Outlined.RssFeed,
            Tab.Settings to Icons.Outlined.Tune,
        )) {
            val on = item == tab
            Row(
                Modifier.weight(1f).fillMaxHeight().clip(CircleShape)
                    .background(if (on) t.ink else Color.Transparent).clickable { onSelect(item) },
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(icon, null, Modifier.size(19.dp), tint = if (on) t.onInk else t.muted)
                Spacer(Modifier.width(8.dp))
                Text(item.name, style = Type.value.copy(fontWeight = if (on) FontWeight.Medium else FontWeight.Normal),
                    color = if (on) t.onInk else t.muted)
            }
        }
    }
}
