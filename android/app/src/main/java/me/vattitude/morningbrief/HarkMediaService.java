package me.vattitude.morningbrief;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import androidx.annotation.Nullable;

public class HarkMediaService extends Service {
    public static final String ACTION_START_PLAYBACK = "me.vattitude.morningbrief.START_PLAYBACK";
    public static final String ACTION_STOP_PLAYBACK = "me.vattitude.morningbrief.STOP_PLAYBACK";
    public static final String ACTION_TOGGLE = "me.vattitude.morningbrief.ACTION_TOGGLE";
    public static final String ACTION_NEXT = "me.vattitude.morningbrief.ACTION_NEXT";
    public static final String ACTION_PREV = "me.vattitude.morningbrief.ACTION_PREV";

    public static final String EXTRA_TITLE = "extra_title";
    public static final String EXTRA_ARTIST = "extra_artist";

    public static final String PLAYBACK_CHANNEL_ID = "hark_playback_channel";
    public static final int NOTIFICATION_ID = 2001;

    private PowerManager.WakeLock wakeLock;
    private MediaSession mediaSession;

    public static void createPlaybackChannel(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = context.getSystemService(NotificationManager.class);
            if (nm != null) {
                NotificationChannel channel = new NotificationChannel(
                    PLAYBACK_CHANNEL_ID,
                    "Audio Playback",
                    NotificationManager.IMPORTANCE_LOW
                );
                channel.setDescription("Background audio playback status");
                channel.setShowBadge(false);
                nm.createNotificationChannel(channel);
            }
        }
    }

    public static void start(Context context, String title, String artist) {
        Intent intent = new Intent(context, HarkMediaService.class);
        intent.setAction(ACTION_START_PLAYBACK);
        intent.putExtra(EXTRA_TITLE, title);
        intent.putExtra(EXTRA_ARTIST, artist);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    public static void stop(Context context) {
        Intent intent = new Intent(context, HarkMediaService.class);
        intent.setAction(ACTION_STOP_PLAYBACK);
        context.startService(intent);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createPlaybackChannel(this);

        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null) {
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "HarkDaily:MediaPlayback");
            wakeLock.setReferenceCounted(false);
        }

        initMediaSession();
    }

    private void initMediaSession() {
        if (mediaSession != null) return;

        mediaSession = new MediaSession(this, "HarkDailyMediaSession");
        mediaSession.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);

        PlaybackState.Builder stateBuilder = new PlaybackState.Builder()
            .setActions(
                PlaybackState.ACTION_PLAY |
                PlaybackState.ACTION_PAUSE |
                PlaybackState.ACTION_PLAY_PAUSE |
                PlaybackState.ACTION_SKIP_TO_NEXT |
                PlaybackState.ACTION_SKIP_TO_PREVIOUS |
                PlaybackState.ACTION_STOP
            )
            .setState(PlaybackState.STATE_PLAYING, PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1.0f);
        mediaSession.setPlaybackState(stateBuilder.build());

        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                MainActivity.dispatchMediaCommand("play");
            }

            @Override
            public void onPause() {
                MainActivity.dispatchMediaCommand("pause");
            }

            @Override
            public void onSkipToNext() {
                MainActivity.dispatchMediaCommand("next");
            }

            @Override
            public void onSkipToPrevious() {
                MainActivity.dispatchMediaCommand("prev");
            }

            @Override
            public void onStop() {
                MainActivity.dispatchMediaCommand("pause");
                stop(HarkMediaService.this);
            }
        });

        mediaSession.setActive(true);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) {
            stopSelf();
            return START_NOT_STICKY;
        }

        String action = intent.getAction();
        if (ACTION_STOP_PLAYBACK.equals(action)) {
            handleStop();
            return START_NOT_STICKY;
        }

        if (ACTION_TOGGLE.equals(action)) {
            MainActivity.dispatchMediaCommand("toggle");
            return START_STICKY;
        }

        if (ACTION_NEXT.equals(action)) {
            MainActivity.dispatchMediaCommand("next");
            return START_STICKY;
        }

        if (ACTION_PREV.equals(action)) {
            MainActivity.dispatchMediaCommand("prev");
            return START_STICKY;
        }

        if (ACTION_START_PLAYBACK.equals(action)) {
            String title = intent.getStringExtra(EXTRA_TITLE);
            String artist = intent.getStringExtra(EXTRA_ARTIST);
            if (title == null || title.trim().isEmpty()) {
                title = "Hark Daily";
            }
            if (artist == null || artist.trim().isEmpty()) {
                artist = "Playing briefing...";
            }

            acquireWakeLock();
            if (mediaSession != null) {
                mediaSession.setActive(true);
            }

            Notification notification = buildPlaybackNotification(title, artist);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } else {
                startForeground(NOTIFICATION_ID, notification);
            }
            return START_STICKY;
        }

        return START_NOT_STICKY;
    }

    private void handleStop() {
        releaseWakeLock();
        if (mediaSession != null) {
            mediaSession.setActive(false);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } else {
            stopForeground(true);
        }
        stopSelf();
    }

    private Notification buildPlaybackNotification(String title, String artist) {
        Intent tapIntent = new Intent(this, MainActivity.class);
        tapIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Intent prevIntent = new Intent(this, HarkMediaService.class).setAction(ACTION_PREV);
        PendingIntent pPrev = PendingIntent.getService(
            this, 101, prevIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Intent toggleIntent = new Intent(this, HarkMediaService.class).setAction(ACTION_TOGGLE);
        PendingIntent pToggle = PendingIntent.getService(
            this, 102, toggleIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Intent nextIntent = new Intent(this, HarkMediaService.class).setAction(ACTION_NEXT);
        PendingIntent pNext = PendingIntent.getService(
            this, 103, nextIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, PLAYBACK_CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        builder.setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFFF59E0B)
            .setContentTitle(title)
            .setContentText(artist)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_TRANSPORT)
            .setContentIntent(contentIntent)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .addAction(new Notification.Action.Builder(
                android.R.drawable.ic_media_previous, "Previous", pPrev
            ).build())
            .addAction(new Notification.Action.Builder(
                android.R.drawable.ic_media_pause, "Pause", pToggle
            ).build())
            .addAction(new Notification.Action.Builder(
                android.R.drawable.ic_media_next, "Next", pNext
            ).build());

        if (mediaSession != null) {
            builder.setStyle(new Notification.MediaStyle()
                .setMediaSession(mediaSession.getSessionToken())
                .setShowActionsInCompactView(0, 1, 2)
            );
        }

        return builder.build();
    }

    private void acquireWakeLock() {
        if (wakeLock != null && !wakeLock.isHeld()) {
            wakeLock.acquire(3 * 60 * 60 * 1000L); // 3 hours timeout safety limit
        }
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
    }

    @Override
    public void onDestroy() {
        releaseWakeLock();
        if (mediaSession != null) {
            mediaSession.setActive(false);
            mediaSession.release();
            mediaSession = null;
        }
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
