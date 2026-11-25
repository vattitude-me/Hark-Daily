package me.vattitude.morningbrief;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;
import androidx.annotation.Nullable;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HarkMediaService extends Service {
    private static final String TAG = "HarkMediaService";

    public static final String ACTION_START_PLAYBACK = "me.vattitude.morningbrief.START_PLAYBACK";
    public static final String ACTION_STOP_PLAYBACK = "me.vattitude.morningbrief.STOP_PLAYBACK";
    public static final String ACTION_TOGGLE = "me.vattitude.morningbrief.ACTION_TOGGLE";
    public static final String ACTION_NEXT = "me.vattitude.morningbrief.ACTION_NEXT";
    public static final String ACTION_PREV = "me.vattitude.morningbrief.ACTION_PREV";

    public static final String EXTRA_TITLE = "extra_title";
    public static final String EXTRA_ARTIST = "extra_artist";
    public static final String EXTRA_ARTWORK_URL = "extra_artwork_url";

    public static final String PLAYBACK_CHANNEL_ID = "hark_playback_channel";
    public static final int NOTIFICATION_ID = 2001;

    static final int MAX_ARTWORK_DIM = 512;
    private static final int MAX_ARTWORK_BYTES = 5 * 1024 * 1024;
    private static final int MAX_CACHE_ENTRIES = 8;
    private static final int MAX_REDIRECTS = 4;
    private static final String ARTWORK_USER_AGENT =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36";

    private PowerManager.WakeLock wakeLock;
    private MediaSession mediaSession;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService artworkExecutor = Executors.newSingleThreadExecutor();
    private final Map<String, Bitmap> artworkCache = Collections.synchronizedMap(
        new LinkedHashMap<String, Bitmap>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Bitmap> eldest) {
                return size() > MAX_CACHE_ENTRIES;
            }
        }
    );

    @Nullable
    private Bitmap fallbackBitmap;
    private volatile boolean isForegroundActive = false;
    private volatile String currentTitle = "Hark Daily";
    private volatile String currentArtist = "Playing briefing...";
    @Nullable
    private volatile String currentArtworkUrl = null;

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
        start(context, title, artist, null);
    }

    public static void start(Context context, String title, String artist, @Nullable String artworkUrl) {
        Intent intent = new Intent(context, HarkMediaService.class);
        intent.setAction(ACTION_START_PLAYBACK);
        intent.putExtra(EXTRA_TITLE, title);
        intent.putExtra(EXTRA_ARTIST, artist);
        if (artworkUrl != null) {
            intent.putExtra(EXTRA_ARTWORK_URL, artworkUrl);
        }
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

    @Nullable
    static String normalizeArtworkUrl(@Nullable String rawUrl) {
        if (rawUrl == null) return null;
        String trimmed = rawUrl.trim();
        if (trimmed.isEmpty()) return null;
        try {
            URI uri = new URI(trimmed);
            if (!"https".equalsIgnoreCase(uri.getScheme())) {
                return null;
            }
            String host = uri.getHost();
            if (host == null || host.isEmpty()) {
                return null;
            }
            if (host.startsWith("[") && host.endsWith("]") && host.length() > 2) {
                host = host.substring(1, host.length() - 1);
            }
            String lowerHost = host.toLowerCase(Locale.ROOT);
            if (isBlockedHost(lowerHost)) {
                return null;
            }
            String path = uri.getPath();
            if (path != null && path.toLowerCase(Locale.ROOT).endsWith(".svg")) {
                return null;
            }
            return trimmed;
        } catch (Exception ignored) {
            return null;
        }
    }

    private static boolean isBlockedHost(String lowerHost) {
        if ("localhost".equals(lowerHost)
                || lowerHost.endsWith(".localhost")
                || lowerHost.endsWith(".local")
                || lowerHost.endsWith(".internal")
                || lowerHost.endsWith(".arpa")) {
            return true;
        }
        if (lowerHost.contains(":")) {
            // Reject loopback, unspecified, unique-local (fc00::/7), link-local (fe80::/10), and IPv4-mapped IPv6 literals.
            return "::".equals(lowerHost)
                || "::1".equals(lowerHost)
                || "0:0:0:0:0:0:0:1".equals(lowerHost)
                || lowerHost.startsWith("fc")
                || lowerHost.startsWith("fd")
                || lowerHost.startsWith("fe8")
                || lowerHost.startsWith("fe9")
                || lowerHost.startsWith("fea")
                || lowerHost.startsWith("feb")
                || lowerHost.startsWith("::ffff:");
        }
        return isPrivateOrReservedIpv4(lowerHost);
    }

    private static boolean isPrivateOrReservedIpv4(String host) {
        String[] parts = host.split("\\.", -1);
        if (parts.length != 4) return false;
        int[] octets = new int[4];
        for (int i = 0; i < 4; i++) {
            if (parts[i].isEmpty()) return false;
            try {
                octets[i] = Integer.parseInt(parts[i]);
            } catch (NumberFormatException ignored) {
                return false;
            }
            if (octets[i] < 0 || octets[i] > 255) return false;
        }
        int a = octets[0];
        int b = octets[1];
        return a == 127
            || a == 10
            || a == 0
            || (a == 169 && b == 254)
            || (a == 192 && b == 168)
            || (a == 172 && b >= 16 && b <= 31)
            || (a == 100 && b >= 64 && b <= 127);
    }

    static int calculateInSampleSize(int width, int height, int maxDim) {
        if (width <= 0 || height <= 0 || maxDim <= 0) {
            return 1;
        }
        int inSampleSize = 1;
        int longest = Math.max(width, height);
        while ((longest / (inSampleSize * 2)) >= maxDim) {
            inSampleSize *= 2;
        }
        return inSampleSize;
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
        setPlayingPlaybackState();

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

    private void setPlayingPlaybackState() {
        if (mediaSession == null) return;
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
            String normalizedArtworkUrl = normalizeArtworkUrl(intent.getStringExtra(EXTRA_ARTWORK_URL));
            if (title == null || title.trim().isEmpty()) {
                title = "Hark Daily";
            }
            if (artist == null || artist.trim().isEmpty()) {
                artist = "Playing briefing...";
            }

            currentTitle = title;
            currentArtist = artist;
            currentArtworkUrl = normalizedArtworkUrl;
            isForegroundActive = true;

            acquireWakeLock();
            if (mediaSession != null) {
                setPlayingPlaybackState();
                mediaSession.setActive(true);
            }

            Bitmap cached = normalizedArtworkUrl != null ? artworkCache.get(normalizedArtworkUrl) : null;
            Bitmap initialArtwork = cached != null ? cached : getFallbackBitmap();
            updateMediaSessionMetadata(title, artist, initialArtwork);

            Notification notification = buildPlaybackNotification(title, artist, initialArtwork);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } else {
                startForeground(NOTIFICATION_ID, notification);
            }

            if (normalizedArtworkUrl != null && cached == null) {
                loadArtworkAsync(normalizedArtworkUrl, title, artist);
            }
            return START_STICKY;
        }

        return START_NOT_STICKY;
    }

    private void handleStop() {
        isForegroundActive = false;
        currentArtworkUrl = null;
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

    @Nullable
    private Bitmap getFallbackBitmap() {
        if (fallbackBitmap == null) {
            fallbackBitmap = BitmapFactory.decodeResource(getResources(), R.drawable.ic_hark_logo);
            if (fallbackBitmap == null) {
                fallbackBitmap = BitmapFactory.decodeResource(getResources(), R.mipmap.ic_launcher);
            }
        }
        return fallbackBitmap;
    }

    private void updateMediaSessionMetadata(String title, String artist, @Nullable Bitmap artwork) {
        if (mediaSession == null) return;
        MediaMetadata.Builder meta = new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, title)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
            .putString(MediaMetadata.METADATA_KEY_ALBUM, "Hark Daily");
        if (artwork != null) {
            meta.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, artwork);
            meta.putBitmap(MediaMetadata.METADATA_KEY_ART, artwork);
        }
        mediaSession.setMetadata(meta.build());
    }

    private void loadArtworkAsync(final String targetUrl, final String expectedTitle, final String expectedArtist) {
        artworkExecutor.execute(() -> {
            if (!isForegroundActive || !targetUrl.equals(currentArtworkUrl)) {
                return;
            }
            Bitmap loaded = artworkCache.get(targetUrl);
            if (loaded == null) {
                loaded = fetchAndScaleBitmap(targetUrl);
                if (loaded != null) {
                    artworkCache.put(targetUrl, loaded);
                }
            }
            if (loaded == null) {
                return;
            }
            final Bitmap finalBitmap = loaded;
            mainHandler.post(() -> {
                if (!isForegroundActive || mediaSession == null || !targetUrl.equals(currentArtworkUrl)) {
                    return;
                }
                updateMediaSessionMetadata(currentTitle, currentArtist, finalBitmap);
                NotificationManager nm = getSystemService(NotificationManager.class);
                if (nm != null) {
                    nm.notify(NOTIFICATION_ID, buildPlaybackNotification(currentTitle, currentArtist, finalBitmap));
                }
            });
        });
    }

    @Nullable
    private Bitmap fetchAndScaleBitmap(String startUrl) {
        try {
            byte[] bytes = downloadImageBytes(startUrl);
            if (bytes == null || bytes.length == 0) {
                return null;
            }
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
                return null;
            }

            BitmapFactory.Options decodeOpts = new BitmapFactory.Options();
            decodeOpts.inSampleSize = calculateInSampleSize(bounds.outWidth, bounds.outHeight, MAX_ARTWORK_DIM);
            decodeOpts.inPreferredConfig = Bitmap.Config.ARGB_8888;
            Bitmap decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, decodeOpts);
            if (decoded == null) {
                return null;
            }
            int w = decoded.getWidth();
            int h = decoded.getHeight();
            int longest = Math.max(w, h);
            if (longest <= MAX_ARTWORK_DIM) {
                return decoded;
            }
            float scale = (float) MAX_ARTWORK_DIM / (float) longest;
            int targetW = Math.max(1, Math.round(w * scale));
            int targetH = Math.max(1, Math.round(h * scale));
            Bitmap scaled = Bitmap.createScaledBitmap(decoded, targetW, targetH, true);
            if (scaled != decoded) {
                decoded.recycle();
            }
            return scaled;
        } catch (Exception e) {
            Log.w(TAG, "Artwork decode failed", e);
            return null;
        }
    }

    @Nullable
    private byte[] downloadImageBytes(String startUrl) {
        String current = startUrl;
        for (int hop = 0; hop <= MAX_REDIRECTS; hop++) {
            String safeUrl = normalizeArtworkUrl(current);
            if (safeUrl == null) {
                return null;
            }
            HttpURLConnection conn = null;
            try {
                URL url = new URL(safeUrl);
                String host = url.getHost();
                if (host != null && !host.isEmpty()) {
                    InetAddress addr = InetAddress.getByName(host);
                    if (addr.isAnyLocalAddress()
                            || addr.isLoopbackAddress()
                            || addr.isLinkLocalAddress()
                            || addr.isSiteLocalAddress()
                            || addr.isMulticastAddress()) {
                        return null;
                    }
                }
                conn = (HttpURLConnection) url.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(6000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("User-Agent", ARTWORK_USER_AGENT);
                conn.setRequestProperty("Accept", "image/*,*/*;q=0.8");
                // Match web referrerpolicy="no-referrer" so publisher CDNs do not hotlink-block.

                int code = conn.getResponseCode();
                if (code == HttpURLConnection.HTTP_MOVED_TEMP
                        || code == HttpURLConnection.HTTP_MOVED_PERM
                        || code == HttpURLConnection.HTTP_SEE_OTHER
                        || code == 307
                        || code == 308) {
                    String location = conn.getHeaderField("Location");
                    if (location == null || location.isEmpty()) {
                        return null;
                    }
                    URI resolved = new URI(safeUrl).resolve(location);
                    current = resolved.toString();
                    continue;
                }
                if (code < 200 || code >= 300) {
                    return null;
                }
                int declaredLen = conn.getContentLength();
                if (declaredLen > MAX_ARTWORK_BYTES) {
                    return null;
                }
                try (InputStream is = conn.getInputStream();
                     ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                    byte[] buf = new byte[8192];
                    int total = 0;
                    int n;
                    while ((n = is.read(buf)) != -1) {
                        total += n;
                        if (total > MAX_ARTWORK_BYTES) {
                            return null;
                        }
                        out.write(buf, 0, n);
                    }
                    return out.toByteArray();
                }
            } catch (Exception e) {
                Log.w(TAG, "Artwork download failed", e);
                return null;
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        return null;
    }

    private Notification buildPlaybackNotification(String title, String artist, @Nullable Bitmap largeIcon) {
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

        if (largeIcon != null) {
            builder.setLargeIcon(largeIcon);
        }

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
        isForegroundActive = false;
        currentArtworkUrl = null;
        artworkExecutor.shutdownNow();
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
