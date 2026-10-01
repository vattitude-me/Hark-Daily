package me.vattitude.morningbrief.ui

import org.json.JSONArray
import org.json.JSONObject

data class Chapter(val id: String, val kind: String, val title: String, val start: Double, val end: Double, val section: String?)

data class Card(
    val id: String, val section: String, val headline: String, val summary: String, val url: String,
    val source: String, val also: List<String>, val image: String?, val start: Double, val end: Double,
)

data class SectionInfo(val key: String, val title: String, val emoji: String, val count: Int)

/** A saved briefing (the same JSON as the server's), shaped for the screen. */
data class Briefing(
    val date: String, val title: String, val duration: Double, val intro: String, val weather: String?,
    val sections: List<SectionInfo>, val chapters: List<Chapter>, val cards: List<Card>, val notes: List<String>,
) {
    companion object {
        private fun JSONArray?.objects(): List<JSONObject> = if (this == null) emptyList() else (0 until length()).map { getJSONObject(it) }

        fun from(j: JSONObject): Briefing {
            val wx = j.optJSONObject("weather")?.let {
                "${it.optString("city")} · ${it.optInt("now")}° now, high ${it.optInt("high")}°, ${it.optString("conditions")}"
            }
            return Briefing(
                date = j.optString("date"),
                title = j.optString("title"),
                duration = j.optDouble("duration", 0.0),
                intro = j.optString("intro"),
                weather = wx,
                sections = j.optJSONArray("sections").objects().map {
                    SectionInfo(it.optString("key"), it.optString("title"), it.optString("emoji"), it.optInt("count"))
                },
                chapters = j.optJSONArray("chapters").objects().map {
                    Chapter(it.optString("id"), it.optString("kind"), it.optString("title"), it.optDouble("start"),
                        it.optDouble("end"), it.optString("section").ifEmpty { null })
                },
                cards = j.optJSONArray("stories").objects().map { c ->
                    val also = c.optJSONArray("also")
                    Card(
                        id = c.optString("id"), section = c.optString("section"), headline = c.optString("headline"),
                        summary = c.optString("summary"), url = c.optString("url"), source = c.optString("source"),
                        also = if (also == null) emptyList() else (0 until also.length()).map { also.getString(it) },
                        image = c.optString("image").takeIf { it.startsWith("http") },
                        start = c.optDouble("start"), end = c.optDouble("end"),
                    )
                },
                notes = j.optJSONArray("notes").objects().map { it.optString("message") }.filter { it.isNotBlank() },
            )
        }
    }
}
