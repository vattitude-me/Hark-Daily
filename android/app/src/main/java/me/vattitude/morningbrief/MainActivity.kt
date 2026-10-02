package me.vattitude.morningbrief

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import me.vattitude.morningbrief.ui.isDark
import me.vattitude.morningbrief.ui.AppViewModel
import me.vattitude.morningbrief.ui.MorningBriefTheme
import me.vattitude.morningbrief.ui.Root

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleShare(intent)
        if (savedInstanceState == null) handleSignIn(intent)
        setContent {
            val appearance by vm.appearance.collectAsState()
            val dark = isDark(appearance)
            DisposableEffect(dark) {
                val bars = if (dark) SystemBarStyle.dark(Color.TRANSPARENT)
                else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
                onDispose {}
            }
            MorningBriefTheme(appearance) {
                Root(vm)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShare(intent)
        handleSignIn(intent)
    }

    override fun onStart() {
        super.onStart()
        vm.onOpen()
    }

    override fun onStop() {
        super.onStop()
        vm.onClose()
    }

    /** Google sign-in finishing: the browser tab hands back me.vattitude.morningbrief://auth?code=... */
    private fun handleSignIn(intent: Intent?) {
        val uri = intent?.data ?: return
        if (intent.action != Intent.ACTION_VIEW || uri.scheme != packageName || uri.host != "auth") return
        vm.finishGoogle(uri)
    }

    /** A link shared from the browser opens the Sources tab with it filled in. */
    private fun handleShare(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
        val url = Regex("https?://\\S+").find(text)?.value ?: return
        vm.shared(url)
    }
}
