package me.vattitude.morningbrief.work

import android.Manifest
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import me.vattitude.morningbrief.MorningBriefApp
import me.vattitude.morningbrief.R
import me.vattitude.morningbrief.pipeline.KOKORO_VOICES
import me.vattitude.morningbrief.pipeline.KokoroPack
import me.vattitude.morningbrief.pipeline.kokoroVoice

/** Downloads the Kokoro voices in the background, so leaving the app doesn't stop it. */
class VoicePackWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val app = context.applicationContext as MorningBriefApp

    override suspend fun getForegroundInfo(): ForegroundInfo = foreground(0f)

    override suspend fun doWork(): Result {
        runCatching { setForeground(foreground(0f)) }
        _state.value = State(running = true)
        var last = -1
        return try {
            KokoroPack.install(applicationContext) { fraction ->
                _state.value = State(running = true, fraction = fraction)
                val pct = (fraction * 100).toInt()
                if (pct != last && canNotify()) {
                    last = pct
                    app.getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(fraction))
                }
            }
            // They downloaded it to hear it: switch to the natural voice unless one is already chosen.
            val st = app.repo.settings
            if (kokoroVoice(st.voice) == null) app.repo.saveSettings(st.copy(voice = KOKORO_VOICES.first().id))
            _state.value = State(done = true)
            Result.success()
        } catch (e: CancellationException) {
            _state.value = State()
            throw e
        } catch (e: Exception) {
            _state.value = State(error = "The download stopped: ${e.message ?: e.javaClass.simpleName}. Try again.")
            Result.failure()
        }
    }

    private fun canNotify() = ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED

    private fun notification(fraction: Float) =
        NotificationCompat.Builder(applicationContext, MorningBriefApp.CHANNEL_BUILD)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Downloading natural voices")
            .setContentText("${(fraction * 100).toInt()}% of 130 MB")
            .setProgress(100, (fraction * 100).toInt(), fraction <= 0f)
            .setOngoing(true)
            .setSilent(true)
            .build()

    private fun foreground(fraction: Float) =
        ForegroundInfo(NOTIFICATION_ID, notification(fraction), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)

    data class State(val running: Boolean = false, val fraction: Float = 0f, val done: Boolean = false, val error: String? = null)

    companion object {
        private const val WORK = "voice-pack"
        private const val NOTIFICATION_ID = 43

        private val _state = MutableStateFlow(State())
        val state: StateFlow<State> = _state

        fun start(context: Context) {
            _state.value = State(running = true)
            val request = OneTimeWorkRequestBuilder<VoicePackWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(WORK, ExistingWorkPolicy.KEEP, request)
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK)
            _state.value = State()
        }
    }
}
