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
    public static final int NOTIFICATION_PERMISSION_REQUEST = 1001;
    public static final int BRIEFING_NOTIFICATION_ID = 3001;

    public static WeakReference<MainActivity> activeInstance;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        activeInstance = new WeakReference<>(this);

        initNotificationChannels();
        requestNotificationPermissionIfNeeded();
        setupWindowInsets();
        configureSmartShell();
    }

    public static void dispatchMediaCommand(String action) {
        MainActivity act = activeInstance != null ? activeInstance.get() : null;
        if (act != null) {
            WebView webView = act.getBridge() != null ? act.getBridge().getWebView() : null;
            if (webView != null) {
                act.runOnUiThread(() -> {
                    switch (action) {
                        case "toggle":
                            webView.evaluateJavascript("window.player?.toggle?.();", null);
                            break;
                        case "play":
                            webView.evaluateJavascript("window.player?.audio?.play?.();", null);
                            break;
                        case "pause":
                            webView.evaluateJavascript("window.player?.audio?.pause?.();", null);
                            break;
                        case "next":
                            webView.evaluateJavascript("window.player?.nextChapter?.();", null);
                            break;
                        case "prev":
                            webView.evaluateJavascript("window.player?.prevChapter?.();", null);
                            break;
                    }
                });
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == NOTIFICATION_PERMISSION_REQUEST) {
            boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            WebView webView = getBridge() != null ? getBridge().getWebView() : null;
            if (webView != null) {
                webView.post(() -> webView.evaluateJavascript(
                    "window.dispatchEvent(new CustomEvent('hark-native-notification-permission', { detail: { granted: " + granted + " } }));",
                    null
                ));
            }
        }
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

    public void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION_REQUEST);
            }
        }
    }

    private void setupWindowInsets() {
        android.view.View content = findViewById(android.R.id.content);
        if (content != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(content, (v, windowInsets) -> {
                androidx.core.graphics.Insets insets = windowInsets.getInsets(
                    androidx.core.view.WindowInsetsCompat.Type.statusBars() |
                    androidx.core.view.WindowInsetsCompat.Type.displayCutout()
                );
                androidx.core.graphics.Insets navInsets = windowInsets.getInsets(
                    androidx.core.view.WindowInsetsCompat.Type.navigationBars()
                );
                float density = getResources().getDisplayMetrics().density;
                int topDp = density > 0 ? Math.round(insets.top / density) : 0;
                int bottomDp = density > 0 ? Math.round(navInsets.bottom / density) : 0;

                WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                if (webView != null && topDp > 0) {
                    final int finalTop = topDp;
                    final int finalBottom = bottomDp;
                    webView.post(() -> webView.evaluateJavascript(
                        "document.documentElement.style.setProperty('--safe-area-inset-top', '" + finalTop + "px');" +
                        "document.documentElement.style.setProperty('--safe-area-inset-bottom', '" + finalBottom + "px');" +
                        "document.documentElement.classList.add('native-shell');",
                        null
                    ));
                }
                return windowInsets;
            });
        }
    }

    private void configureSmartShell() {
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            WebView.setWebContentsDebuggingEnabled(true);

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

    private final android.os.Handler stopHandler = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable stopRunnable = () -> HarkMediaService.stop(this);

    public void handlePlaybackState(boolean isPlaying, String title, String artist) {
        stopHandler.removeCallbacks(stopRunnable);
        if (isPlaying) {
            HarkMediaService.start(this, title, artist);
        } else {
            // Debounce service shutdown by 3 seconds so sequential clip transitions
            // (which momentarily fire pause before next clip play) don't destroy
            // the foreground service and trigger Android 14+ background kill.
            stopHandler.postDelayed(stopRunnable, 3000);
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
        if (isFinishing()) {
            HarkMediaService.stop(this);
        }
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
        public boolean hasNotificationPermission() {
            MainActivity act = activityRef.get();
            if (act == null) return false;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                return act.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
            }
            return NotificationManagerCompat.from(act).areNotificationsEnabled();
        }

        @JavascriptInterface
        public void requestNotificationPermission() {
            MainActivity act = activityRef.get();
            if (act != null) {
                act.runOnUiThread(act::requestNotificationPermissionIfNeeded);
            }
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

        @JavascriptInterface
        public int getSafeAreaTop() {
            MainActivity act = activityRef.get();
            if (act == null) return 36;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                try {
                    android.view.WindowInsets insets = act.getWindowManager().getCurrentWindowMetrics().getWindowInsets();
                    android.graphics.Insets sb = insets.getInsets(
                        android.view.WindowInsets.Type.statusBars() | android.view.WindowInsets.Type.displayCutout()
                    );
                    float density = act.getResources().getDisplayMetrics().density;
                    int dp = density > 0 ? Math.round(sb.top / density) : 0;
                    if (dp > 0) return dp;
                } catch (Exception ignored) {}
            }
            try {
                int resourceId = act.getResources().getIdentifier("status_bar_height", "dimen", "android");
                if (resourceId > 0) {
                    int px = act.getResources().getDimensionPixelSize(resourceId);
                    float density = act.getResources().getDisplayMetrics().density;
                    int dp = density > 0 ? Math.round(px / density) : 0;
                    if (dp > 0) return dp;
                }
            } catch (Exception ignored) {}
            return 36;
        }

        @JavascriptInterface
        public int getSafeAreaBottom() {
            MainActivity act = activityRef.get();
            if (act == null) return 0;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                try {
                    android.view.WindowInsets insets = act.getWindowManager().getCurrentWindowMetrics().getWindowInsets();
                    android.graphics.Insets sb = insets.getInsets(android.view.WindowInsets.Type.navigationBars());
                    float density = act.getResources().getDisplayMetrics().density;
                    return density > 0 ? Math.round(sb.bottom / density) : 0;
                } catch (Exception ignored) {}
            }
            return 0;
        }

        @JavascriptInterface
        public void setStatusBarTheme(String theme) {
            MainActivity act = activityRef.get();
            if (act != null) {
                act.runOnUiThread(() -> {
                    boolean isDark = "dark".equalsIgnoreCase(theme);
                    androidx.core.view.WindowInsetsControllerCompat insetsController =
                        androidx.core.view.WindowCompat.getInsetsController(act.getWindow(), act.getWindow().getDecorView());
                    if (insetsController != null) {
                        insetsController.setAppearanceLightStatusBars(!isDark);
                    }
                });
            }
        }
    }
}
