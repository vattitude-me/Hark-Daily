package me.vattitude.morningbrief;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import com.getcapacitor.BridgeActivity;
import java.lang.ref.WeakReference;

public class MainActivity extends BridgeActivity {
    public static final String BRIEFING_CHANNEL_ID = "hark_daily_briefing";
    private static final int NOTIFICATION_PERMISSION_REQUEST = 1001;
    private static final int BRIEFING_NOTIFICATION_ID = 3001;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        initNotificationChannels();
        requestNotificationPermissionIfNeeded();
        configureSmartShell();
    }

    private void initNotificationChannels() {
        HarkMediaService.createPlaybackChannel(this);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel briefingChannel = new NotificationChannel(
                    BRIEFING_CHANNEL_ID,
                    "Daily Briefings",
                    NotificationManager.IMPORTANCE_DEFAULT
                );
                briefingChannel.setDescription("Morning and evening audio briefing updates");
                briefingChannel.setShowBadge(true);
                nm.createNotificationChannel(briefingChannel);
            }
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION_REQUEST);
            }
        }
    }

    private void configureSmartShell() {
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            WebSettings settings = webView.getSettings();
            settings.setMediaPlaybackRequiresUserGesture(false);
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);

            webView.addJavascriptInterface(new HarkNativeBridge(this), "HarkNative");
        }
    }

    public void applyKeepScreenOn(boolean keepOn) {
        if (keepOn) {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } else {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }

    public void handlePlaybackState(boolean isPlaying, String title, String artist) {
        if (isPlaying) {
            HarkMediaService.start(this, title, artist);
        } else {
            HarkMediaService.stop(this);
        }
    }

    public void showLocalNotification(String title, String body) {
        Intent tapIntent = new Intent(this, MainActivity.class);
        tapIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, BRIEFING_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFFF59E0B)
            .setContentTitle(title != null && !title.isEmpty() ? title : "Hark Daily Briefing")
            .setContentText(body != null && !body.isEmpty() ? body : "Your audio briefing is ready to listen.")
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(contentIntent);

        NotificationManagerCompat nm = NotificationManagerCompat.from(this);
        try {
            nm.notify(BRIEFING_NOTIFICATION_ID, builder.build());
        } catch (SecurityException ignored) {
            // Permission not granted
        }
    }

    @Override
    public void onDestroy() {
        applyKeepScreenOn(false);
        HarkMediaService.stop(this);
        super.onDestroy();
    }

    public static class HarkNativeBridge {
        private final WeakReference<MainActivity> activityRef;

        public HarkNativeBridge(MainActivity activity) {
            this.activityRef = new WeakReference<>(activity);
        }

        @JavascriptInterface
        public boolean isNativeShell() {
            return true;
        }

        @JavascriptInterface
        public void setKeepScreenOn(boolean keepOn) {
            MainActivity act = activityRef.get();
            if (act != null) {
                act.runOnUiThread(() -> act.applyKeepScreenOn(keepOn));
            }
        }

        @JavascriptInterface
        public void notifyPlaybackState(boolean isPlaying, String title, String artist) {
            MainActivity act = activityRef.get();
            if (act != null) {
                act.runOnUiThread(() -> act.handlePlaybackState(isPlaying, title, artist));
            }
        }

        @JavascriptInterface
        public void postNotification(String title, String body) {
            MainActivity act = activityRef.get();
            if (act != null) {
                act.runOnUiThread(() -> act.showLocalNotification(title, body));
            }
        }
    }
}
