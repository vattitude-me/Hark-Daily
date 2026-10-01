package me.vattitude.morningbrief.pipeline

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import me.vattitude.morningbrief.data.Repo
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.roundToInt

class BuildFailed(message: String) : Exception(message)

/**
 * The whole morning pipeline, on the phone: the same steps as the server's batch.py for one user.
 *
 *   sources → fetch → rank and dedupe → read the chosen articles → write copy → voice → AAC → save
 */
class Builder(private val context: Context, private val repo: Repo) {

    suspend fun build(progress: suspend (String, Float) -> Unit): JSONObject = withContext(Dispatchers.Default) {
        val started = System.currentTimeMillis()
        val zone = ZoneId.systemDefault()
        val now = ZonedDateTime.now(zone)
        val day = now.toLocalDate().toString()
        val notes = JSONArray()
        fun note(code: String, message: String) = notes.put(JSONObject().put("code", code).put("message", message))

        // 1. Settings and sources ---------------------------------------------------------
        progress("Checking your sources", 0.02f)
        repo.pullSettings()
        val st = repo.settings
        val (all, offline) = repo.sources()
        offline?.let { note("sources_cached", it) }
        val consumed = repo.prefs.consumed
        val wanted = all.filter { it.enabled && !(it.kind == "article" && it.url in consumed) }
        val sources = wanted.mapNotNull { repo.resolve(it) }
            .filterNot { it.kind == "article" && it.url in consumed }
        if (sources.isEmpty()) throw BuildFailed("Switch on at least one source to get a briefing.")

        // 2. Fetch -------------------------------------------------------------------------
        progress("Gathering today's headlines", 0.06f)
        val fetcher = Fetcher()
        val (items, statuses) = fetcher.fetchAll(sources)
        repo.prefs.sourceStatus = JSONObject().apply {
            for ((id, status) in statuses) put(id.toString(), JSONObject().put("status", status)
                .put("count", items.count { it.sourceId == id }).put("at", Instant.now().toString()))
        }
        val failed = sources.filter { !it.builtin && statuses[it.id] != "ok" }
        if (failed.isNotEmpty()) {
            note("sources_failed", "Some of your links couldn't be read: " +
                failed.joinToString(", ") { "${it.name}: ${statuses[it.id]}" }.take(300))
        }
        if (items.isEmpty()) throw BuildFailed("Couldn't reach any news sources. Check your connection and try again.")

        // 3. Rank, skipping what the last two briefings already told ---------------------
        progress("Picking the top stories", 0.15f)
        val limits = SECTIONS.keys.associateWith { (st.stories[it] ?: 0).coerceIn(0, 10) }
        val picked = selectTop(items, limits, Instant.now(), repo.briefings.heard(now.toLocalDate()))
        if (picked.isEmpty()) throw BuildFailed("No new stories turned up. Try again later or add more sources.")
        val stories = picked.values.flatten()

        progress("Reading the full articles", 0.22f)
        fetcher.enrich(stories.map { it.lead })

        // 4. Copy ----------------------------------------------------------------------------
        val writer = StoryWriter(st.groqKey.ifBlank { null })
        val copies = HashMap<String, StoryCopy>()
        var n = 0
        for ((section, group) in picked) for (story in group) {
            progress("Writing summaries", 0.3f + 0.15f * n++ / stories.size)
            copies[story.id] = withContext(Dispatchers.IO) { writer.copy(section, story) }
        }
        writer.notes.forEach { note("ai", it) }

        val wx = if (st.weather) withContext(Dispatchers.IO) { forecast(st.latitude, st.longitude, st.city, zone.id) } else null
        val script = compose(picked, copies, now, spokenWeather(wx), st.name.trim().ifEmpty { null }, st.saySources)

        // 5. Voice and assemble -----------------------------------------------------------------
        val segments = mutableListOf(Triple("intro", script.intro, 0.9))
        for ((section, group) in picked) {
            segments.add(Triple("section:$section", script.sectionLeads.getValue(section), 0.6))
            group.forEachIndexed { i, story ->
                segments.add(Triple(story.id, script.stories.getValue(story.id).spoken, if (i == group.size - 1) 1.2 else 0.8))
            }
        }
        segments.add(Triple("outro", script.outro, 0.8))

        val work = File(context.cacheDir, "build").apply { deleteRecursively(); mkdirs() }
        val out = File(work, "briefing.m4a")
        val marks = HashMap<String, Pair<Double, Double>>()
        val speech = Speech.open(context)
        val voiceName: String?
        try {
            voiceName = speech.setVoice(st.voice)
            speech.setSpeed(st.speed)
            val aac = AacWriter(out)
            try {
                aac.silence(0.35)
                segments.forEachIndexed { i, (key, text, pause) ->
                    progress("Recording your briefing", 0.45f + 0.5f * i / segments.size)
                    val wav = File(work, "$i.wav")
                    speech.toFile(speakable(text), wav)
                    val clip = prepareClip(readWav(wav))
                    wav.delete()
                    val start = aac.seconds
                    aac.write(clip)
                    marks[key] = round2(start) to round2(aac.seconds)
                    aac.silence(pause)
                }
            } finally {
                aac.close()
            }
        } finally {
            speech.close()
        }

        // 6. Save -------------------------------------------------------------------------------
        progress("Saving", 0.97f)
        val doc = document(picked, script, marks, wx, voiceName, now, day, started, notes)
        repo.briefings.save(day, doc, out)
        repo.briefings.cleanup(now.toLocalDate())
        val used = stories.flatMap { s -> s.items.filter { it.kind == "article" } }.map { it.url }
        val articleSources = sources.filter { it.kind == "article" && statuses[it.id] == "ok" }.map { it.url }
        repo.prefs.consumed = consumed + articleSources + used
        work.deleteRecursively()
        doc
    }

    private fun round2(v: Double) = (v * 100).roundToInt() / 100.0

    private fun document(
        picked: Map<String, List<Story>>, script: Script, marks: Map<String, Pair<Double, Double>>, wx: Forecast?,
        voice: String?, now: ZonedDateTime, day: String, started: Long, notes: JSONArray,
    ): JSONObject {
        val chapters = JSONArray()
        val cards = JSONArray()
        fun chapter(id: String, kind: String, title: String, start: Double, end: Double, text: String, section: String? = null) =
            chapters.put(JSONObject().put("id", id).put("kind", kind).put("title", title).put("start", start)
                .put("end", end).put("text", text).apply { section?.let { put("section", it) } })

        chapter("intro", "intro", "Good morning", 0.0, marks.getValue("intro").second, script.intro)
        for ((section, group) in picked) {
            val sStart = marks.getValue("section:$section").first
            chapter("section:$section", "section", SECTIONS.getValue(section).title, sStart, sStart,
                script.sectionLeads.getValue(section), section)
            for (story in group) {
                val copy = script.stories.getValue(story.id)
                val (start, end) = marks.getValue(story.id)
                chapter(story.id, "story", copy.headline, start, end, copy.spoken, section)
                val lead = story.lead
                cards.put(JSONObject()
                    .put("id", story.id).put("section", section).put("headline", copy.headline)
                    .put("original_title", lead.title).put("summary", copy.summary).put("url", lead.url)
                    .put("source", lead.sourceName)
                    .put("also", JSONArray(story.sources.filter { it != lead.sourceName }))
                    .put("links", JSONArray(story.items.take(5).map { JSONObject().put("source", it.sourceName).put("url", it.url) }))
                    .put("image", lead.image?.takeIf { it.startsWith("http://") || it.startsWith("https://") } ?: JSONObject.NULL)
                    .put("published", lead.published?.toString() ?: JSONObject.NULL)
                    .put("start", start).put("end", end).put("writer", copy.writer))
            }
        }
        val (oStart, oEnd) = marks.getValue("outro")
        chapter("outro", "outro", "Sign-off", oStart, oEnd, script.outro)
        val dayName = now.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.ENGLISH)
        return JSONObject()
            .put("date", day)
            .put("title", "$dayName, ${now.month.getDisplayName(TextStyle.FULL, Locale.ENGLISH)} ${now.dayOfMonth}")
            .put("generated_at", Instant.now().toString())
            .put("duration", oEnd + 0.8)
            .put("voice", JSONObject().put("id", voice ?: "default").put("name", voice ?: "Phone default"))
            .put("writer", script.writer)
            .put("weather", wx?.toJson() ?: JSONObject.NULL)
            .put("intro", script.intro)
            .put("sections", JSONArray(picked.map { (k, v) ->
                val s = SECTIONS.getValue(k)
                JSONObject().put("key", k).put("title", s.title).put("emoji", s.emoji).put("count", v.size)
            }))
            .put("chapters", chapters)
            .put("stories", cards)
            .put("notes", notes)
            .put("build_seconds", (System.currentTimeMillis() - started) / 1000.0)
    }
}
