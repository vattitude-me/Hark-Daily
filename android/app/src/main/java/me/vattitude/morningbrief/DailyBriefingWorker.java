package me.vattitude.morningbrief;

import android.content.Context;
import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Background periodic worker checking public Supabase pack_ready status so Android
 * users receive morning episode notifications even without signing in or Firebase/FCM.
 */
public class DailyBriefingWorker extends Worker {
    static final String WORK_NAME = "hark_daily_morning_check";
    private static final String PACK_TIMEZONE = "America/Toronto";
    private static final String FALLBACK_BODY = "Tap to listen to today's morning episode.";
    private static final Pattern TITLE_FIELD_RE = Pattern.compile("\"title\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"");

    public DailyBriefingWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context ctx = getApplicationContext();
        if (!NotificationHelper.hasNotificationPermission(ctx) || !NotificationHelper.isMorningAlertsEnabled(ctx)) {
            return Result.success();
        }

        String today = torontoToday();
        if (today.equals(NotificationHelper.getLastNotifiedDate(ctx))) {
            return Result.success();
        }

        String baseUrl = NotificationHelper.getSupabaseUrl(ctx);
        String apiKey = NotificationHelper.getSupabaseKey(ctx);
        try {
            String readyUrl = baseUrl + "/rest/v1/voice_notes?date=eq." + today + "&note_key=eq.pack_ready&select=date&limit=1";
            String readyBody = fetchBody(readyUrl, apiKey);
            if (!hasNonEmptyJsonArray(readyBody)) {
                return Result.success();
            }

            String topSection = topSectionForEdition(NotificationHelper.getEdition(ctx));
            String storyUrl = baseUrl + "/rest/v1/story_audio?date=eq." + today
                + "&section=eq." + topSection + "&rank=eq.1&select=title&limit=1";
            String storyBody = fetchBody(storyUrl, apiKey);
            String body = extractLeadTitle(storyBody);

            NotificationHelper.showBriefingNotification(ctx, "☀️ Today's episode is ready", body);
            NotificationHelper.setLastNotifiedDate(ctx, today);
            return Result.success();
        } catch (Exception exc) {
            return Result.retry();
        }
    }

    static String torontoToday() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone(PACK_TIMEZONE));
        return fmt.format(new Date());
    }

    static String topSectionForEdition(String edition) {
        if ("us".equalsIgnoreCase(edition)) return "top_us";
        if ("in".equalsIgnoreCase(edition)) return "top_in";
        return "top";
    }

    static boolean hasNonEmptyJsonArray(String jsonBody) {
        if (jsonBody == null) return false;
        String trimmed = jsonBody.trim();
        return trimmed.startsWith("[") && trimmed.length() > 2 && !trimmed.equals("[]") && trimmed.contains("{");
    }

    static String extractLeadTitle(String jsonBody) {
        if (!hasNonEmptyJsonArray(jsonBody)) {
            return FALLBACK_BODY;
        }
        Matcher m = TITLE_FIELD_RE.matcher(jsonBody);
        if (m.find()) {
            String raw = m.group(1)
                .replace("\\\"", "\"")
                .replace("\\n", " ")
                .replace("\\t", " ")
                .replace("\\\\", "\\")
                .trim();
            if (!raw.isEmpty()) {
                return raw;
            }
        }
        return FALLBACK_BODY;
    }

    private static String fetchBody(String endpoint, String apiKey) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(endpoint).openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(10_000);
        conn.setRequestProperty("apikey", apiKey);
        conn.setRequestProperty("Authorization", "Bearer " + apiKey);
        conn.setRequestProperty("Accept", "application/json");
        int code = conn.getResponseCode();
        if (code < 200 || code >= 300) {
            conn.disconnect();
            throw new IllegalStateException("HTTP " + code);
        }
        try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line);
            }
            return sb.toString();
        } finally {
            conn.disconnect();
        }
    }

    static void schedule(Context ctx) {
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();
        PeriodicWorkRequest work = new PeriodicWorkRequest.Builder(
            DailyBriefingWorker.class,
            1, TimeUnit.HOURS,
            15, TimeUnit.MINUTES
        ).setConstraints(constraints).build();

        WorkManager.getInstance(ctx.getApplicationContext()).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            work
        );
    }

    static void cancel(Context ctx) {
        WorkManager.getInstance(ctx.getApplicationContext()).cancelUniqueWork(WORK_NAME);
    }

    static void ensureScheduledIfEnabled(Context ctx) {
        if (NotificationHelper.hasNotificationPermission(ctx) && NotificationHelper.isMorningAlertsEnabled(ctx)) {
            schedule(ctx);
        } else {
            cancel(ctx);
        }
    }
}
