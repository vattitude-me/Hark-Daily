package me.vattitude.morningbrief.work

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.workDataOf
import me.vattitude.morningbrief.data.Settings
import java.time.Duration
import java.time.LocalDate
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

/**
 * The morning build starts about [LEAD_MINUTES] before the "ready by" time, so the briefing is waiting when you wake.
 * Android may hold it back a little in deep sleep; opening the app catches up.
 */
object Scheduler {
    private const val DAILY = "daily-build"
    private const val NOW = "build-now"
    const val LEAD_MINUTES = 90L

    fun nextRun(settings: Settings, now: ZonedDateTime = ZonedDateTime.now()): ZonedDateTime {
        var at = now.toLocalDate().atTime(settings.readyHour, settings.readyMinute).atZone(now.zone).minusMinutes(LEAD_MINUTES)
        while (!at.isAfter(now.plusMinutes(1))) at = at.plusDays(1)
        return at
    }

    /** (Re)plans tomorrow's build. [fromWorker] keeps the running build alive instead of replacing it. */
    fun schedule(context: Context, settings: Settings, fromWorker: Boolean = false) {
        val wm = WorkManager.getInstance(context)
        if (!settings.daily) {
            wm.cancelUniqueWork(DAILY)
            return
        }
        val delay = Duration.between(ZonedDateTime.now(), nextRun(settings)).toMillis().coerceAtLeast(0)
        val request = OneTimeWorkRequestBuilder<BuildWorker>()
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInputData(workDataOf(BuildWorker.SCHEDULED to true))
            .addTag(DAILY)
            .build()
        wm.enqueueUniqueWork(DAILY, if (fromWorker) ExistingWorkPolicy.APPEND_OR_REPLACE else ExistingWorkPolicy.REPLACE, request)
    }

    /** Records [date]'s briefing again in the voice now chosen; shares the "now" slot so it never overlaps a build. */
    fun revoice(context: Context, date: String) {
        val request = OneTimeWorkRequestBuilder<BuildWorker>()
            .setInputData(workDataOf(BuildWorker.REVOICE to date))
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
    }

    fun buildNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<BuildWorker>()
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
    }

    /**
     * When the app opens after this morning's build time and there's no briefing yet (the phone slept through it,
     * or it was off), build now. Only once a day, so a failing build doesn't restart on every open.
     */
    fun catchUp(context: Context, settings: Settings, hasToday: Boolean, lastAttempt: String?) {
        schedule(context, settings)
        if (!settings.daily || hasToday) return
        val today = LocalDate.now()
        if (lastAttempt == today.toString()) return
        val now = ZonedDateTime.now()
        val start = today.atTime(settings.readyHour, settings.readyMinute).atZone(now.zone).minusMinutes(LEAD_MINUTES)
        if (now.isAfter(start)) buildNow(context)
    }
}
