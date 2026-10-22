package me.vattitude.morningbrief.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import me.vattitude.morningbrief.pipeline.DEFAULT_STORIES
import me.vattitude.morningbrief.pipeline.MAX_PER_SECTION
import me.vattitude.morningbrief.pipeline.SECTIONS
import me.vattitude.morningbrief.pipeline.packVoice
import me.vattitude.morningbrief.pipeline.pickPackVoice
import me.vattitude.morningbrief.ui.Briefing
import me.vattitude.morningbrief.ui.Card
import me.vattitude.morningbrief.ui.Chapter
import me.vattitude.morningbrief.ui.SectionInfo
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalTime
import java.util.concurrent.TimeUnit

/** One clip on the briefing's timeline: a story, one of the spoken notes, or a breath between two. */
data class Clip(
    val id: String, val title: String, val url: String,
    val duration: Double, val start: Double, val end: Double, val note: Boolean,
    /** True for the silent clip that separates two voiced ones. */
    val gap: Boolean = false,
)

/**
 * A breath between two clips, in seconds. Without it the end of one story runs into the start of
 * the next and the two read as a single sentence. Mirrors BREATH in web/js/storypack.js.
 */
const val BREATH = 0.8

/**
 * The marker note a narrator's day carries once every clip and every spoken note is published
 * (app/storypack.py). Without it the day is still being recorded and must not be played: half a
 * day's clips in one voice and half in another is worse than waiting.
 */
const val PACK_READY = "pack_ready"

/** A listener's briefing, assembled from the shared day's clips. */
data class Pack(val briefing: Briefing, val clips: List<Clip>, val version: String)

/** Which greeting to open with, by the listener's local hour (mirrors app/storypack.py). */
fun greetingKey(hour: Int = LocalTime.now().hour): String = when {
    hour < 12 -> "greeting_morning"
    hour < 17 -> "greeting_afternoon"
    else -> "greeting_evening"
}

/** The per-section counts a listener asked for (0 = off), clamped to 0..[MAX_PER_SECTION]. */
fun lineup(stories: Map<String, Int>): Map<String, Int> {
    val mapped = SECTIONS.keys.associateWith { (stories[it] ?: 0).coerceIn(0, MAX_PER_SECTION) }
    return if (mapped.values.any { it > 0 }) mapped else DEFAULT_STORIES
}

private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

internal fun clipUrl(path: String) = "$SUPABASE_URL/storage/v1/object/public/briefings/$path"

/**
 * Turns the day's shared clips into one listener's briefing: the greeting, then each
 * section's spoken intro before its first story. Mirrors web/js/storypack.js, so the phone
 * and the browser assemble exactly the same thing from the same rows.
 *
 * Nothing here is per-user except *which* clips are chosen — the audio is generated once
 * for everyone, so cost never grows with the number of listeners.
 */
object StoryPack {
    /**
     * Fetches the day's shared rows and notes once and assembles both Full and Rapid Fire packs.
     */
    suspend fun fetchBoth(
        supabase: Supabase,
        date: String,
        stories: Map<String, Int>,
        voice: String? = null,
        sectionOrder: List<String> = emptyList(),
    ): Pair<Pack?, Pack?> {
        var day = date
        var rows = supabase.storyAudio(day)
        if (rows.length() == 0) {
            val latest = runCatching { supabase.latestStoryDate() }.getOrNull()
            if (latest != null && latest != day) {
                day = latest
                rows = supabase.storyAudio(day)
            }
        }
        if (rows.length() == 0) return null to null
        val every = rows.objects()
        val notes = runCatching { supabase.voiceNotes(day) }.getOrDefault(JSONArray())
        val noteRows = notes.objects()
        val full = assemble(day, every, noteRows, stories, voice, sectionOrder, mode = "full")
        val rapid = assemble(day, every, noteRows, stories, voice, sectionOrder, mode = "rapid")
        return full to rapid
    }

    /**
     * [date] is the day the listener asked for. When that day has no pack — the nightly job hasn't
     * published yet, or it wasn't a news day — the most recent published day is used instead, and
     * the returned pack carries that day in [Briefing.date] so the caller can say where it's from.
     * Null means there is genuinely nothing recorded yet.
     */
    suspend fun fetch(supabase: Supabase, date: String, stories: Map<String, Int>,
                      voice: String? = null, sectionOrder: List<String> = emptyList(), mode: String = "full"): Pack? {
        var day = date
        var rows = supabase.storyAudio(day)
        if (rows.length() == 0) {
            val latest = runCatching { supabase.latestStoryDate() }.getOrNull()
            if (latest != null && latest != day) {
                day = latest
                rows = supabase.storyAudio(day)
            }
        }
        if (rows.length() == 0) return null
        val every = rows.objects()
        val notes = runCatching { supabase.voiceNotes(day) }.getOrDefault(JSONArray())
        val noteRows = notes.objects()
        return assemble(day, every, noteRows, stories, voice, sectionOrder, mode)
    }

    internal fun assemble(
        day: String,
        every: List<JSONObject>,
        noteRows: List<JSONObject>,
        stories: Map<String, Int>,
        voice: String? = null,
        sectionOrder: List<String> = emptyList(),
        mode: String = "full",
    ): Pack? {
        if (every.isEmpty()) return null
        // Every narrator is published each morning, so the day's rows hold all of them:
        // play the one this listener picked.
        val spokenBy = pickPackVoice(every.map { it.optString("voice") }, voice)
        val all = if (spokenBy == null) every else every.filter { it.optString("voice") == spokenBy }
        // Playable only once the narrator's clips and framing are all published.
        val hasReadyMarkers = noteRows.any { it.optString("note_key") == PACK_READY }
        if (hasReadyMarkers && noteRows.none { it.optString("note_key") == PACK_READY && it.optString("voice") == spokenBy }) return null

        val isRapid = mode == "rapid"
        val order = effectiveSectionOrder(sectionOrder)
        val wanted = if (isRapid) {
            val rapidWanted = LinkedHashMap<String, Int>()
            for (key in SECTIONS.keys) rapidWanted[key] = 0
            val topClips = all.filter { it.optString("section") == "top" }
            val topCount = minOf(5, topClips.size)
            rapidWanted["top"] = topCount
            var remaining = 5 - topCount
            if (remaining > 0) {
                for (key in order) {
                    if (key == "top") continue
                    val avail = all.filter { it.optString("section") == key }.size
                    val take = minOf(remaining, avail)
                    if (take > 0) {
                        rapidWanted[key] = take
                        remaining -= take
                    }
                    if (remaining <= 0) break
                }
            }
            if (rapidWanted.values.none { it > 0 }) {
                rapidWanted["top"] = 5
            }
            rapidWanted
        } else {
            lineup(stories)
        }

        val noteByKey = noteRows.filter { spokenBy == null || it.optString("voice") == spokenBy }
            .associateBy { it.optString("note_key") }

        val clips = mutableListOf<Clip>()
        val cards = mutableListOf<Card>()
        val chapters = mutableListOf<Chapter>()
        val counts = LinkedHashMap<String, Int>()
        var cursor = 0.0

        /** A silent clip between two voiced ones, so a story never starts on the last word. */
        fun breath() {
            if (cursor <= 0.0) return
            clips += Clip("gap-${clips.size}", clips.last().title, "", BREATH, cursor, cursor + BREATH,
                note = false, gap = true)
            cursor += BREATH
        }

        fun sayNote(key: String) {
            val note = noteByKey[key] ?: return
            breath()
            val duration = note.optDouble("duration", 0.0)
            val text = note.optString("text")
            clips += Clip(key, text, clipUrl(note.optString("audio_path")), duration, cursor, cursor + duration, note = true)
            chapters += Chapter(key, "note", text, cursor, cursor + duration, null)
            cursor += duration
        }

        sayNote(greetingKey())

        for (key in order) {
            val count = wanted[key] ?: 0
            if (count <= 0) continue
            val chosen = all.filter { it.optString("section") == key }.sortedBy { it.optInt("rank") }.take(count)
            if (chosen.isEmpty()) continue
            if (!isRapid) {
                sayNote("intro_$key")
            }
            for (row in chosen) {
                breath()
                val duration = row.optDouble("duration", 0.0)
                val id = "$key-${row.optInt("rank")}"
                val title = row.optString("title")
                val start = cursor
                val end = cursor + duration
                clips += Clip(id, title, clipUrl(row.optString("audio_path")), duration, start, end, note = false)
                cards += Card(
                    id = id, section = key, headline = title, summary = row.optString("script"),
                    url = row.optString("url"), source = row.optString("source").ifEmpty { "The Guardian" },
                    also = emptyList(), image = row.optString("image").takeIf { it.startsWith("http") },
                    start = start, end = end,
                )
                chapters += Chapter(id, "story", title, start, end, key)
                counts[key] = (counts[key] ?: 0) + 1
                cursor += duration
            }
        }
        // The sign-off, so a brief does not stop dead on the last story's final word.
        sayNote("outro")
        if (clips.isEmpty()) return null

        val version = all.map { it.optString("created_at") }.maxOrNull().orEmpty()
        val briefing = Briefing(
            date = day,
            title = if (isRapid) "Rapid Fire · Top 5 Stories" else "Your briefing",
            duration = cursor,
            intro = "",
            weather = null,
            sections = order.filter { counts.containsKey(it) && SECTIONS.containsKey(it) }
                .map { key ->
                    val s = SECTIONS.getValue(key)
                    SectionInfo(key, s.title, s.emoji, counts[key] ?: 0)
                },
            chapters = chapters,
            cards = cards,
            notes = emptyList(),
            // The pack is voiced by the server's cloned narrator, not a phone voice, so
            // voiceId stays empty: there is nothing on this device to re-record.
            voiceName = packVoice(spokenBy).name,
            version = version,
            mode = if (isRapid) "rapid" else "full",
        )
        return Pack(briefing, clips, version)
    }

    /**
     * Fallback for visitors and guest listeners without an active session. Supabase restricts the
     * `story_audio` table to authenticated sessions, but publishes a daily showcase sample
     * for each narrator into public storage every morning.
     */
    suspend fun fetchShowcase(
        voice: String? = null,
        stories: Map<String, Int> = DEFAULT_STORIES,
        sectionOrder: List<String> = emptyList(),
        mode: String = "full",
    ): Pack? = withContext(Dispatchers.IO) {
        val target = voice ?: "c3po_reference"
        val candidates = listOf(
            "$SUPABASE_URL/storage/v1/object/public/briefings/showcase/pack.json",
            "$SUPABASE_URL/storage/v1/object/public/briefings/showcase/sample-$target.json",
            "$SUPABASE_URL/storage/v1/object/public/briefings/showcase/sample-c3po_reference.json",
            "$SUPABASE_URL/storage/v1/object/public/briefings/showcase/sample.json"
        )
        val client = OkHttpClient.Builder().callTimeout(10, TimeUnit.SECONDS).build()
        for (urlStr in candidates) {
            val pack = runCatching {
                val req = Request.Builder().url(urlStr).build()
                val jsonStr = client.newCall(req).execute().use { res ->
                    if (!res.isSuccessful) null else res.body?.string()
                } ?: return@runCatching null
                val root = JSONObject(jsonStr)
                val rowsArr = root.optJSONArray("story_audio") ?: root.optJSONArray("rows")
                val notesArr = root.optJSONArray("voice_notes") ?: root.optJSONArray("notes")
                val day = root.optString("date").ifEmpty { root.optJSONObject("briefing")?.optString("date").orEmpty() }
                if (rowsArr != null && rowsArr.length() > 0 && day.isNotEmpty()) {
                    val assembled = assemble(day, rowsArr.objects(), notesArr?.objects() ?: emptyList(), stories, voice, sectionOrder, mode)
                    if (assembled != null) return@runCatching assembled
                }
                val bJson = root.optJSONObject("briefing") ?: return@runCatching null
                val baseBriefing = Briefing.from(bJson)
                val isRapid = mode == "rapid"
                val briefing = baseBriefing.copy(
                    mode = if (isRapid) "rapid" else "full",
                    title = if (isRapid) "Rapid Fire · Top 5 Stories" else baseBriefing.title,
                    cards = if (isRapid) baseBriefing.cards.take(5) else baseBriefing.cards,
                )
                val clipsArr = bJson.optJSONArray("clips")
                val clips = (0 until (clipsArr?.length() ?: 0)).map { i ->
                    val c = clipsArr!!.getJSONObject(i)
                    Clip(
                        id = "clip_$i",
                        title = c.optString("title", briefing.title),
                        url = c.optString("url"),
                        duration = c.optDouble("duration", 0.0),
                        start = c.optDouble("start", 0.0),
                        end = c.optDouble("end", 0.0),
                        note = c.optBoolean("note", false),
                        gap = c.optBoolean("gap", false)
                    )
                }
                Pack(briefing = briefing, clips = clips, version = bJson.optString("generated_at", "v1"))
            }.getOrNull()
            if (pack != null) return@withContext pack
        }
        null
    }
}
