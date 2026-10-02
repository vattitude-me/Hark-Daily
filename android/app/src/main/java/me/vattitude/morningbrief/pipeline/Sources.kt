package me.vattitude.morningbrief.pipeline

import org.json.JSONObject
import java.net.URLEncoder

/** A briefing section. [stories] is the default count; 0 leaves it off. */
data class Section(val key: String, val title: String, val emoji: String, val topic: String, val stories: Int = 0) {
    /** A topic picked from the catalog (World, Sports...), as opposed to Local, Following and My Sources. */
    val isCategory: Boolean get() = key !in setOf("local", "follow", "custom")
}

/**
 * A news source. [id] is the Supabase row id when signed in; local sources use negative ids.
 * [kind] is feed, page, article or auto (not yet detected).
 */
data class Source(
    val id: Long,
    val name: String,
    val url: String,
    val section: String,
    val weight: Double = 1.0,
    val kind: String = "feed",
    val feedUrl: String? = null,
    val enabled: Boolean = true,
    val builtin: Boolean = false,
)

/** app/catalog/sources.json, shared with the worker and bundled as a resource. */
private val CATALOG: JSONObject by lazy {
    val stream = Source::class.java.getResourceAsStream("/sources.json") ?: error("The source catalog is missing")
    JSONObject(stream.bufferedReader().use { it.readText() })
}

/** Every section, in the order a briefing reads them. */
val SECTIONS: LinkedHashMap<String, Section> by lazy {
    val arr = CATALOG.getJSONArray("sections")
    LinkedHashMap<String, Section>().apply {
        for (i in 0 until arr.length()) {
            val j = arr.getJSONObject(i)
            put(j.getString("key"), Section(j.getString("key"), j.getString("title"), j.getString("emoji"),
                j.getString("topic"), j.optInt("stories")))
        }
    }
}

val DEFAULT_STORIES: Map<String, Int> get() = SECTIONS.mapValues { it.value.stories }

/** The catalog's sources. Their ids are negative and stable; signed in, the Supabase row's id replaces it. */
val BUILTIN_SOURCES: List<Source> by lazy {
    val arr = CATALOG.getJSONArray("sources")
    (0 until arr.length()).map { i ->
        val j = arr.getJSONObject(i)
        Source(-100_000L - i, j.getString("name"), j.getString("url"), j.getString("section"), j.optDouble("weight", 1.0),
            feedUrl = j.getString("url"), builtin = true)
    }
}

/** News for a city: its own outlets where the catalog knows them, and Google News for anywhere. */
fun localSources(city: String): List<Source> {
    val name = city.substringBefore(',').trim()
    if (name.isEmpty()) return emptyList()
    val local = CATALOG.getJSONObject("local")
    val key = name.lowercase().let { local.getJSONObject("aliases").optString(it).ifEmpty { it } }
    val known = local.getJSONObject("cities").optJSONArray(key)
    val everywhere = local.getJSONArray("everywhere")
    val picks = (0 until (known?.length() ?: 0)).map { known!!.getJSONObject(it) } +
        (0 until everywhere.length()).map { everywhere.getJSONObject(it) }
    val encoded = URLEncoder.encode(name, "UTF-8").replace("+", "%20")
    return picks.mapIndexed { i, j ->
        val url = j.getString("url").replace("{city}", encoded)
        Source(-200_000L - i, j.getString("name").replace("{city}", name), url, "local", j.optDouble("weight", 1.0),
            feedUrl = url, builtin = true)
    }
}

/** A news search feed for a person, team or topic. */
fun followUrl(query: String): String =
    CATALOG.getJSONObject("follow").getString("url").replace("{query}", URLEncoder.encode(query.trim(), "UTF-8"))

fun isFollowUrl(url: String): Boolean = url.startsWith(followUrl("").substringBefore('?'))

/** Names to try in the Follow box. */
val FOLLOW_EXAMPLES: List<String> by lazy {
    CATALOG.getJSONObject("follow").getJSONArray("examples").let { a -> (0 until a.length()).map { a.getString(it) } }
}
