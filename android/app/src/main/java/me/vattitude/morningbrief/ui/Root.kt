package me.vattitude.morningbrief.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Headphones
import androidx.compose.material.icons.outlined.RssFeed
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier

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
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                for ((t, icon) in listOf(
                    Tab.Today to Icons.Outlined.Headphones,
                    Tab.Sources to Icons.Outlined.RssFeed,
                    Tab.Settings to Icons.Outlined.Settings,
                )) {
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { vm.tab.value = t },
                        icon = { Icon(icon, contentDescription = null) },
                        label = { Text(t.name) },
                    )
                }
            }
        },
    ) { padding ->
        val m = Modifier.padding(padding)
        when (tab) {
            Tab.Today -> TodayScreen(vm, m)
            Tab.Sources -> SourcesScreen(vm, m)
            Tab.Settings -> SettingsScreen(vm, m)
        }
    }
}
