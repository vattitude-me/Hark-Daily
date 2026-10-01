package me.vattitude.morningbrief

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import me.vattitude.morningbrief.data.Repo

class MorningBriefApp : Application() {
    val repo by lazy { Repo(this) }

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_BUILD, "Building your briefing", NotificationManager.IMPORTANCE_LOW)
                .apply { description = "Shown while the morning briefing is being put together" },
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_READY, "Briefing ready", NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = "When your briefing is ready, or couldn't be made" },
        )
    }

    companion object {
        const val CHANNEL_BUILD = "build"
        const val CHANNEL_READY = "ready"
    }
}
