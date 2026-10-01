package me.vattitude.morningbrief.data

import org.json.JSONArray
import org.json.JSONObject

/**
 * The user's settings. The fields shared with the web app keep the web app's JSON names
 * (profiles.settings), so a signed-in user's choices follow them between web and phone.
 */
data class Settings(
    val name: String = "",
    val city: String = "Toronto",
    val latitude: Double = 43.6532,
    val longitude: Double = -79.3832,
    val weather: Boolean = true,
    val saySources: Boolean = false,
    val stories: Map<String, Int> = mapOf("canada" to 6, "tech" to 6, "custom" to 4),
    /** Supabase ids of built-in sources switched off (signed in). */
    val disabledSources: Set<Long> = emptySet(),
    /** URLs of built-in sources switched off (signed out). */
    val disabledUrls: Set<String> = emptySet(),
    // Phone-only settings.
    val daily: Boolean = true,
    val readyBy: String = "07:00",
    val voice: String? = null,
    val speed: Float = 1.0f,
    val groqKey: String = "",
    val welcomed: Boolean = false,
) {
    val readyHour: Int get() = readyBy.substringBefore(':').toIntOrNull()?.coerceIn(0, 23) ?: 7
    val readyMinute: Int get() = readyBy.substringAfter(':').toIntOrNull()?.coerceIn(0, 59) ?: 0

    fun toJson(): JSONObject = sharedJson()
        .put("disabled_urls", JSONArray(disabledUrls.toList()))
        .put("android_daily", daily)
        .put("ready_by", readyBy)
        .put("android_voice", voice ?: JSONObject.NULL)
        .put("android_speed", speed.toDouble())
        .put("groq_key", groqKey)
        .put("welcomed", welcomed)

    /** Only the fields the web app also uses. */
    fun sharedJson(): JSONObject = JSONObject()
        .put("name", name)
        .put("city", city)
        .put("latitude", latitude)
        .put("longitude", longitude)
        .put("weather", weather)
        .put("say_sources", saySources)
        .put("stories", JSONObject(stories))
        .put("disabled_sources", JSONArray(disabledSources.toList()))

    /** Takes the shared fields from the server's copy, keeping phone-only settings. */
    fun withShared(remote: JSONObject): Settings = copy(
        name = remote.optString("name", name),
        city = remote.optString("city", city),
        latitude = remote.optDouble("latitude", latitude),
        longitude = remote.optDouble("longitude", longitude),
        weather = remote.optBoolean("weather", weather),
        saySources = remote.optBoolean("say_sources", saySources),
        stories = remote.optJSONObject("stories")?.let { s -> stories.mapValues { (k, v) -> s.optInt(k, v) } } ?: stories,
        disabledSources = remote.optJSONArray("disabled_sources")?.let { a -> (0 until a.length()).map { a.getLong(it) }.toSet() }
            ?: disabledSources,
    )

    companion object {
        fun fromJson(json: JSONObject?): Settings {
            json ?: return Settings()
            val base = Settings().withShared(json)
            return base.copy(
                disabledUrls = json.optJSONArray("disabled_urls")?.let { a -> (0 until a.length()).map { a.getString(it) }.toSet() }
                    ?: emptySet(),
                daily = json.optBoolean("android_daily", true),
                readyBy = json.optString("ready_by", "07:00"),
                voice = json.optString("android_voice").takeIf { it.isNotEmpty() && it != "null" },
                speed = json.optDouble("android_speed", 1.0).toFloat(),
                groqKey = json.optString("groq_key", ""),
                welcomed = json.optBoolean("welcomed", false),
            )
        }
    }
}
