package me.vattitude.morningbrief.work

import android.Manifest
import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import me.vattitude.morningbrief.MainActivity
import me.vattitude.morningbrief.MorningBriefApp
import me.vattitude.morningbrief.R
import me.vattitude.morningbrief.data.Repo
import me.vattitude.morningbrief.pipeline.BuildFailed
import me.vattitude.morningbrief.pipeline.Builder
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate

class BuildWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val app = context.applicationContext as MorningBriefApp

    override suspend fun getForegroundInfo(): ForegroundInfo = foreground("Getting started", 0f)

    override suspend fun doWork(): Result {
        val scheduled = inputData.getBoolean(SCHEDULED, false)
        val repo = app.repo
        if (!BuildState.lock.tryLock()) return Result.success()
        val result = try {
            attempt(repo, scheduled)
        } finally {
            if (BuildState.progress.value.running) BuildState.update(BuildState.Progress())
            BuildState.lock.unlock()
        }
        // A retry keeps its place in the chain; otherwise plan tomorrow.
        if (scheduled && result != Result.retry()) Scheduler.schedule(applicationContext, repo.settings, fromWorker = true)
        return result
    }

    private suspend fun attempt(repo: Repo, scheduled: Boolean): Result {
        runCatching { setForeground(foreground("Getting started", 0f)) }
        repo.prefs.lastBuild = JSONObject().put("day", LocalDate.now().toString()).put("started", Instant.now().toString())
        BuildState.update(BuildState.Progress(running = true, step = "Getting started"))
        return try {
            val doc = Builder(applicationContext, repo).build { step, fraction ->
                BuildState.update(BuildState.Progress(running = true, step = step, fraction = fraction))
                runCatching { setForeground(foreground(step, fraction)) }
            }
            repo.prefs.lastBuild = repo.prefs.lastBuild.put("ok", true).put("finished", Instant.now().toString())
            BuildState.update(BuildState.Progress())
            notifyDone("Your briefing is ready", readySummary(doc))
            Result.success()
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            val message = (e as? BuildFailed)?.message ?: "Something went wrong: ${e.message ?: e.javaClass.simpleName}"
            repo.prefs.lastBuild = repo.prefs.lastBuild.put("ok", false).put("error", message)
            BuildState.update(BuildState.Progress(error = message))
            if (scheduled && e !is BuildFailed && runAttemptCount < 2) return Result.retry()
            notifyDone("Couldn't make today's briefing", message)
            Result.failure()
        }
    }

    private fun readySummary(doc: JSONObject): String {
        val minutes = (doc.optDouble("duration") / 60).let { if (it < 1) 1 else Math.round(it).toInt() }
        val count = doc.optJSONArray("stories")?.length() ?: 0
        return "$count stories, about $minutes min. Tap to listen."
    }

    private fun openApp(): PendingIntent = PendingIntent.getActivity(
        applicationContext, 0,
        Intent(applicationContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun foreground(step: String, fraction: Float): ForegroundInfo {
        val n: Notification = NotificationCompat.Builder(applicationContext, MorningBriefApp.CHANNEL_BUILD)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Making your briefing")
            .setContentText(step)
            .setProgress(100, (fraction * 100).toInt(), fraction <= 0f)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(openApp())
            .build()
        return ForegroundInfo(PROGRESS_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    }

    private fun notifyDone(title: String, text: String) {
        val n = NotificationCompat.Builder(applicationContext, MorningBriefApp.CHANNEL_READY)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(openApp())
            .build()
        val allowed = ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        if (allowed) NotificationManagerCompat.from(applicationContext).notify(DONE_ID, n)
    }

    companion object {
        const val SCHEDULED = "scheduled"
        private const val PROGRESS_ID = 41
        private const val DONE_ID = 42
    }
}
