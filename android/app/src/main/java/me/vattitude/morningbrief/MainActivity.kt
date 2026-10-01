package me.vattitude.morningbrief

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import me.vattitude.morningbrief.ui.AppViewModel
import me.vattitude.morningbrief.ui.MorningBriefTheme
import me.vattitude.morningbrief.ui.Root

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleShare(intent)
        setContent {
            MorningBriefTheme {
                Root(vm)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShare(intent)
    }

    override fun onStart() {
        super.onStart()
        vm.onOpen()
    }

    override fun onStop() {
        super.onStop()
        vm.onClose()
    }

    /** A link shared from the browser opens the Sources tab with it filled in. */
    private fun handleShare(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
        val url = Regex("https?://\\S+").find(text)?.value ?: return
        vm.shared(url)
    }
}
