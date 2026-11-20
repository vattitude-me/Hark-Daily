package me.vattitude.morningbrief;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

/**
 * Shared notification channel, permission, and preference helpers used by both
 * MainActivity and DailyBriefingWorker.
 */
final class NotificationHelper {
    static final String BRIEFING_CHANNEL_ID = "hark_daily_briefing";
    static final int BRIEFING_NOTIFICATION_ID = 3001;

    static final String DEFAULT_SUPABASE_URL = "https://oohbmeffdncyzujmeqcz.supabase.co";
    static final String DEFAULT_SUPABASE_KEY = "sb_publishable_HgWQGelTuCEU6ayqFdY4Cg_F_-VVEYv";

    private static final String PREFS_NAME = "hark_daily_prefs";
    private static final String KEY_ALERTS_ENABLED = "morning_alerts_enabled";
    private static final String KEY_LAST_NOTIFIED_DATE = "last_notified_date";
    private static final String KEY_SUPABASE_URL = "supabase_url";
    private static final String KEY_SUPABASE_KEY = "supabase_key";
    private static final String KEY_EDITION = "edition";

    private NotificationHelper() {}

    static void ensureChannels(Context ctx) {
        HarkMediaService.createPlaybackChannel(ctx);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = ctx.getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel briefingChannel = new NotificationChannel(
                    BRIEFING_CHANNEL_ID,
                    "Daily episodes",
                    NotificationManager.IMPORTANCE_DEFAULT
                );
                briefingChannel.setDescription("New daily episode alerts");
                briefingChannel.setShowBadge(true);
                nm.createNotificationChannel(briefingChannel);
            }
        }
    }

    static boolean hasNotificationPermission(Context ctx) {
        if (ctx == null) return false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
        }
        return NotificationManagerCompat.from(ctx).areNotificationsEnabled();
    }

    static void showBriefingNotification(Context ctx, String title, String body) {
        ensureChannels(ctx);
        Intent tapIntent = new Intent(ctx, MainActivity.class);
        tapIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
            ctx,
            0,
            tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(ctx, BRIEFING_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFFF59E0B)
            .setContentTitle(title != null && !title.isEmpty() ? title : "Hark Daily")
            .setContentText(body != null && !body.isEmpty() ? body : "Your new episode is ready to play.")
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(contentIntent);

        NotificationManagerCompat nm = NotificationManagerCompat.from(ctx);
        try {
            nm.notify(BRIEFING_NOTIFICATION_ID, builder.build());
        } catch (SecurityException ignored) {
            // Notification permission revoked
        }
    }

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    static boolean isMorningAlertsEnabled(Context ctx) {
        return prefs(ctx).getBoolean(KEY_ALERTS_ENABLED, true);
    }

    static void setMorningAlertsEnabled(Context ctx, boolean enabled) {
        prefs(ctx).edit().putBoolean(KEY_ALERTS_ENABLED, enabled).apply();
    }

    static String getLastNotifiedDate(Context ctx) {
        return prefs(ctx).getString(KEY_LAST_NOTIFIED_DATE, "");
    }

    static void setLastNotifiedDate(Context ctx, String day) {
        prefs(ctx).edit().putString(KEY_LAST_NOTIFIED_DATE, day != null ? day : "").apply();
    }

    static void saveConfig(Context ctx, String supabaseUrl, String supabaseKey, String edition) {
        SharedPreferences.Editor ed = prefs(ctx).edit();
        if (supabaseUrl != null && !supabaseUrl.trim().isEmpty()) {
            ed.putString(KEY_SUPABASE_URL, supabaseUrl.trim().replaceAll("/+$", ""));
        }
        if (supabaseKey != null && !supabaseKey.trim().isEmpty()) {
            ed.putString(KEY_SUPABASE_KEY, supabaseKey.trim());
        }
        if (edition != null && !edition.trim().isEmpty()) {
            ed.putString(KEY_EDITION, edition.trim().toLowerCase());
        }
        ed.apply();
    }

    static String getSupabaseUrl(Context ctx) {
        return prefs(ctx).getString(KEY_SUPABASE_URL, DEFAULT_SUPABASE_URL);
    }

    static String getSupabaseKey(Context ctx) {
        return prefs(ctx).getString(KEY_SUPABASE_KEY, DEFAULT_SUPABASE_KEY);
    }

    static String getEdition(Context ctx) {
        return prefs(ctx).getString(KEY_EDITION, "ca");
    }
}
