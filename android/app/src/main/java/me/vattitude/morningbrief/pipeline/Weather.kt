package me.vattitude.morningbrief.pipeline

import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.abs
import kotlin.math.roundToInt

/** A one-line forecast from Open-Meteo (free, no key), as in app/weather.py. */

data class Forecast(val city: String, val now: Int, val high: Int, val low: Int, val code: Int,
                    val conditions: String, val precip: Int?) {
    fun toJson(): JSONObject = JSONObject().put("city", city).put("now", now).put("high", high).put("low", low)
        .put("code", code).put("conditions", conditions).put("precip", precip ?: JSONObject.NULL)
}

data class Place(val name: String, val latitude: Double, val longitude: Double, val region: String)

private val WMO = mapOf(
    0 to "clear skies", 1 to "mostly clear skies", 2 to "partly cloudy skies", 3 to "overcast skies",
    45 to "fog", 48 to "freezing fog", 51 to "light drizzle", 53 to "drizzle", 55 to "heavy drizzle",
    56 to "freezing drizzle", 57 to "freezing drizzle", 61 to "light rain", 63 to "rain", 65 to "heavy rain",
    66 to "freezing rain", 67 to "freezing rain", 71 to "light snow", 73 to "snow", 75 to "heavy snow", 77 to "snow grains",
    80 to "passing showers", 81 to "showers", 82 to "heavy showers", 85 to "snow showers", 86 to "heavy snow showers",
    95 to "thunderstorms", 96 to "thunderstorms with hail", 99 to "thunderstorms with hail",
)

private val client = OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS).build()

fun forecast(lat: Double, lon: Double, city: String, tz: String): Forecast? = runCatching {
    val url = "https://api.open-meteo.com/v1/forecast".toHttpUrl().newBuilder()
        .addQueryParameter("latitude", lat.toString())
        .addQueryParameter("longitude", lon.toString())
        .addQueryParameter("timezone", tz)
        .addQueryParameter("forecast_days", "1")
        .addQueryParameter("current", "temperature_2m,weather_code")
        .addQueryParameter("daily", "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max")
        .build()
    client.newCall(Request.Builder().url(url).build()).execute().use { resp ->
        check(resp.isSuccessful)
        val data = JSONObject(resp.body!!.string())
        val now = data.getJSONObject("current")
        val daily = data.getJSONObject("daily")
        val code = daily.getJSONArray("weather_code").getInt(0)
        Forecast(
            city = city,
            now = now.getDouble("temperature_2m").roundToInt(),
            high = daily.getJSONArray("temperature_2m_max").getDouble(0).roundToInt(),
            low = daily.getJSONArray("temperature_2m_min").getDouble(0).roundToInt(),
            code = code,
            conditions = WMO[code] ?: "mixed conditions",
            precip = daily.optJSONArray("precipitation_probability_max")?.let { if (it.isNull(0)) null else it.getInt(0) },
        )
    }
}.getOrNull()

fun spokenWeather(info: Forecast?): String? {
    info ?: return null
    fun deg(v: Int) = if (v < 0) "minus ${abs(v)}" else v.toString()
    var line = "In ${info.city} it's ${deg(info.now)} degrees right now, heading for a high of ${deg(info.high)} with ${info.conditions}."
    if (info.precip != null && info.precip >= 50 && info.code < 51) {
        line += " There's a ${info.precip} percent chance of rain, so grab an umbrella."
    }
    return line
}

/** City search for the settings screen (Open-Meteo geocoding, also free). */
fun searchPlaces(query: String): List<Place> = runCatching {
    val url = "https://geocoding-api.open-meteo.com/v1/search".toHttpUrl().newBuilder()
        .addQueryParameter("name", query).addQueryParameter("count", "6").addQueryParameter("language", "en").build()
    client.newCall(Request.Builder().url(url).build()).execute().use { resp ->
        val results = JSONObject(resp.body!!.string()).optJSONArray("results") ?: return@use emptyList()
        (0 until results.length()).map { i ->
            val r = results.getJSONObject(i)
            Place(r.getString("name"), r.getDouble("latitude"), r.getDouble("longitude"),
                listOfNotNull(r.optString("admin1").ifEmpty { null }, r.optString("country").ifEmpty { null }).joinToString(", "))
        }
    }
}.getOrDefault(emptyList())
