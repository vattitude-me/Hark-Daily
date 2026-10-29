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
    /** True for banter clips from the podcast hosts. */
    val banter: Boolean = false,
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

/** The marker clip a host pair's day carries once its banter is published (app/podcast.py). */
const val PODCAST_READY_KEY = "podcast_ready"

/** Total banter, in seconds, a podcast brief may add around the news: the news is the priority. */
const val PODCAST_BUDGET = 90.0

/** Sections that get a teaser, so a six-section lineup doesn't open with a minute of chat. */
const val MAX_TEASERS = 3

data class PodcastPlan(
    val hosts: String,
    val open: JSONObject,
    val teasers: List<JSONObject>,
    val bridges: Map<String, JSONObject>,
    val close: JSONObject,
    val banter: Double,
)

fun stableHash(text: String): Long {
    var n = 0L
    for (ch in text) {
        n = (n * 31L + ch.code.toLong()) and 0xFFFFFFFFL
    }
    return n
}

fun planPodcast(clips: List<JSONObject>, sections: List<String>, seed: String = ""): PodcastPlan? {
    if (clips.isEmpty()) return null
    val ready = clips.filter { it.optString("clip_key") == PODCAST_READY_KEY }
    val hosts = ready.map { it.optString("hosts") }.sorted().firstOrNull() ?: return null
    val mine = clips.filter { it.optString("hosts") == hosts && it.optString("clip_key") != PODCAST_READY_KEY && it.optString("audio_path").isNotEmpty() }
    val byKey = mine.associateBy { it.optString("clip_key") }
    fun variant(kind: String): JSONObject? {
        val all = mine.filter { it.optString("clip_key").startsWith("pod_${kind}_") }
            .sortedBy { it.optString("clip_key") }
        if (all.isEmpty()) return null
        val idx = (stableHash("$seed:$kind") % all.size.toLong()).toInt()
        return all[idx]
    }
    val open = variant("open") ?: return null
    val close = variant("close") ?: return null
    fun dur(c: JSONObject) = c.optDouble("duration", 0.0)
    var used = dur(open) + dur(close)
    val teasers = mutableListOf<JSONObject>()
    for (sec in sections.take(MAX_TEASERS)) {
        val c = byKey["pod_tease_$sec"]
        if (c != null && used + dur(c) <= PODCAST_BUDGET) {
            teasers += c
            used += dur(c)
        }
    }
    val bridges = mutableMapOf<String, JSONObject>()
    for (sec in sections) {
        val c = byKey["pod_bridge_$sec"]
        if (c != null && used + dur(c) <= PODCAST_BUDGET) {
            bridges[sec] = c
            used += dur(c)
        }
    }
    return PodcastPlan(hosts, open, teasers, bridges, close, used)
}

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
 * Extract clean body summary from broadcast script by stripping repeated headline,
 * podcast banter connectors, and editorial section prefixes (e.g. "The news:").
 */
fun stripHeadlineAndFiller(headline: String, scriptOrSummary: String): String {
    var text = scriptOrSummary.trim()
    if (text.isEmpty()) return ""
    val cleanTitle = headline.trim().trimEnd('.', '!', '?', ':')
    if (cleanTitle.isNotEmpty()) {
        val pattern = Regex("^" + Regex.escape(cleanTitle) + "[.!?]?\\s*", RegexOption.IGNORE_CASE)
        text = pattern.replace(text, "").trim()
    }
    val connPattern = Regex("^(?:Here are the details:|Here's what you need to know:|Taking a closer look:|Here's what's happening:|According to the reporting:|In the details:|Behind the headline:)\\s*", RegexOption.IGNORE_CASE)
    text = connPattern.replace(text, "").trim()
    val labelPattern = Regex("^(?:The news|Why it matters|What to know|What happened|The big picture|From the source|Between the lines|Catch up quick|By the numbers|What they're saying|What they are saying|What's next|The backstory|Yes, but|Details|Context|Zoom in|Zoom out|What to watch|State of play):\\s*", RegexOption.IGNORE_CASE)
    text = labelPattern.replace(text, "").trim()
    if (text.isNotEmpty() && text[0].isLowerCase()) {
        text = text.replaceFirstChar { it.uppercase() }
    }
    return text.ifEmpty { scriptOrSummary.trim() }
}

/**
 * Turns the day's shared clips into one listener's briefing: the greeting, then each
 * section's spoken intro before its first story. Mirrors web/js/storypack.js, so the phone
 * and the browser assemble exactly the same thing from the same rows.
 *
 * Nothing here is per-user except *which* clips are chosen — the audio is generated once
 * for everyone, so cost never grows with the number of listeners.
 */
object StoryPack {
    data class PackSet(val full: Pack?, val podcast: Pack?, val rapid: Pack?)

    /**
     * Fetches the day's shared rows, notes, and podcast clips, assembling full, podcast, and rapid packs.
     */
    suspend fun fetchAll(
        supabase: Supabase,
        date: String,
        stories: Map<String, Int>,
        voice: String? = null,
        sectionOrder: List<String> = emptyList(),
    ): PackSet {
        var day = date
        var rows = supabase.storyAudio(day)
        if (rows.length() == 0) {
            val latest = runCatching { supabase.latestStoryDate() }.getOrNull()
            if (latest != null && latest != day) {
                day = latest
                rows = supabase.storyAudio(day)
            }
        }
        if (rows.length() == 0) return PackSet(null, null, null)
        val every = rows.objects()
        val notes = runCatching { supabase.voiceNotes(day) }.getOrDefault(JSONArray())
        val noteRows = notes.objects()
        val podcasts = runCatching { supabase.podcastClips(day) }.getOrDefault(JSONArray())
        val podRows = podcasts.objects()
        val full = assemble(day, every, noteRows, stories, voice, sectionOrder, mode = "full")
        val podcast = assemble(day, every, noteRows, stories, voice, sectionOrder, mode = "podcast", podcastClips = podRows)
        val rapid = assemble(day, every, noteRows, stories, voice, sectionOrder, mode = "rapid")
        return PackSet(full, podcast, rapid)
    }

    /**
     * Backward-compatible fetcher returning full and secondary pack (podcast if available, else rapid).
     */
    suspend fun fetchBoth(
        supabase: Supabase,
        date: String,
        stories: Map<String, Int>,
        voice: String? = null,
        sectionOrder: List<String> = emptyList(),
    ): Pair<Pack?, Pack?> {
        val s = fetchAll(supabase, date, stories, voice, sectionOrder)
        return s.full to (s.podcast ?: s.rapid)
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
        val podcastClips = if (mode == "podcast") {
            runCatching { supabase.podcastClips(day) }.getOrDefault(JSONArray()).objects()
        } else emptyList()
        return assemble(day, every, noteRows, stories, voice, sectionOrder, mode, podcastClips)
    }

    internal fun assemble(
        day: String,
        every: List<JSONObject>,
        noteRows: List<JSONObject>,
        stories: Map<String, Int>,
        voice: String? = null,
        sectionOrder: List<String> = emptyList(),
        mode: String = "full",
        podcastClips: List<JSONObject> = emptyList(),
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

        val pod = if (mode == "podcast") {
            val chosenRank1Sections = order.filter { key -> (wanted[key] ?: 0) > 0 && all.any { it.optString("section") == key && it.optInt("rank") == 1 } }
            planPodcast(podcastClips, chosenRank1Sections, "$day:${spokenBy ?: ""}")
        } else null
        val isPodcast = pod != null

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

        fun banterTitle(clipKey: String, sectionKey: String? = null): String {
            if (clipKey.startsWith("pod_open")) return "Welcome · Today's preview"
            if (clipKey.startsWith("pod_tease")) {
                val sec = sectionKey ?: clipKey.removePrefix("pod_tease_")
                val secName = SECTIONS[sec]?.title ?: sec
                return "Coming up · $secName"
            }
            if (clipKey.startsWith("pod_bridge")) {
                val sec = sectionKey ?: clipKey.removePrefix("pod_bridge_")
                val secName = SECTIONS[sec]?.title ?: sec
                return "Up next · $secName"
            }
            if (clipKey.startsWith("pod_close")) return "That's today's briefing · Signing off"
            return "Today's Briefing"
        }

        fun noteTitle(noteKey: String): String {
            if (noteKey.startsWith("greeting_morning")) return "Good morning · Daily briefing"
            if (noteKey.startsWith("greeting_afternoon")) return "Good afternoon · Daily briefing"
            if (noteKey.startsWith("greeting_evening")) return "Good evening · Daily briefing"
            if (noteKey.startsWith("intro_")) {
                val sec = noteKey.removePrefix("intro_")
                val secName = SECTIONS[sec]?.title ?: sec
                return "Here are the ${secName.lowercase()} stories"
            }
            if (noteKey == "outro") return "That's today's brief"
            return "Today's Briefing"
        }

        fun sayNote(key: String) {
            val note = noteByKey[key] ?: return
            breath()
            val duration = note.optDouble("duration", 0.0)
            val text = note.optString("text")
            val title = noteTitle(key)
            clips += Clip(key, title, clipUrl(note.optString("audio_path")), duration, cursor, cursor + duration, note = true)
            chapters += Chapter(key, "note", title, cursor, cursor + duration, null, text = text)
            cursor += duration
        }

        fun sayBanter(clip: JSONObject?, sectionKey: String? = null) {
            if (clip == null) return
            breath()
            val duration = clip.optDouble("duration", 0.0)
            val text = clip.optString("text")
            val key = clip.optString("clip_key")
            val path = clip.optString("audio_path")
            val title = banterTitle(key, sectionKey)
            clips += Clip(key, title, clipUrl(path), duration, cursor, cursor + duration, note = true, banter = true)
            chapters += Chapter(key, "note", title, cursor, cursor + duration, sectionKey, text = text)
            cursor += duration
        }

        if (isPodcast) {
            sayBanter(pod!!.open)
            for (teaser in pod.teasers) {
                sayBanter(teaser)
            }
        } else {
            sayNote(greetingKey())
        }

        val podHosts = if (isPodcast) pod!!.hosts.split("+").filter { it.isNotEmpty() } else emptyList()
        var storyIndex = 0
        for (key in order) {
            val count = wanted[key] ?: 0
            if (count <= 0) continue
            val chosen = all.filter { it.optString("section") == key }.sortedBy { it.optInt("rank") }.take(count)
            if (chosen.isEmpty()) continue
            if (!isRapid) {
                if (isPodcast) {
                    sayBanter(pod!!.bridges[key], key)
                } else {
                    sayNote("intro_$key")
                }
            }
            for (row in chosen) {
                breath()
                // In podcast mode, alternate the stories between the two hosts so they co-anchor
                var storyRow = row
                if (isPodcast && podHosts.size >= 2) {
                    val targetVoice = podHosts[storyIndex % podHosts.size]
                    val match = every.firstOrNull { it.optString("section") == key && it.optInt("rank") == row.optInt("rank") && it.optString("voice") == targetVoice }
                    if (match != null) storyRow = match
                    storyIndex++
                }
                val duration = storyRow.optDouble("duration", 0.0)
                val id = "$key-${storyRow.optInt("rank")}"
                val title = storyRow.optString("title")
                val start = cursor
                val end = cursor + duration
                clips += Clip(id, title, clipUrl(storyRow.optString("audio_path")), duration, start, end, note = false)
                val cleanSummary = storyRow.optString("summary").ifEmpty { stripHeadlineAndFiller(title, storyRow.optString("script")) }
                cards += Card(
                    id = id, section = key, headline = title, summary = cleanSummary,
                    url = storyRow.optString("url"), source = storyRow.optString("source").ifEmpty { "The Guardian" },
                    also = emptyList(), image = storyRow.optString("image").takeIf { it.startsWith("http") },
                    start = start, end = end,
                    audioPath = storyRow.optString("audio_path"),
                )
                chapters += Chapter(id, "story", title, start, end, key)
                counts[key] = (counts[key] ?: 0) + 1
                cursor += duration
            }
        }
        // The sign-off, so a brief does not stop dead on the last story's final word.
        if (isPodcast) {
            sayBanter(pod!!.close)
        } else {
            sayNote("outro")
        }
        if (clips.isEmpty()) return null

        val version = all.map { it.optString("created_at") }.maxOrNull().orEmpty()
        val briefing = Briefing(
            date = day,
            title = when {
                isRapid -> "Rapid Fire · Top 5 Stories"
                isPodcast -> "Your briefing · Podcast"
                else -> "Your briefing"
            },
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
            voiceName = if (isPodcast && podHosts.isNotEmpty()) {
                podHosts.joinToString(" & ") { packVoice(it).name }
            } else {
                packVoice(spokenBy).name
            },
            version = version,
            mode = when {
                isRapid -> "rapid"
                isPodcast -> "podcast"
                else -> "full"
            },
            podcastFallback = (mode == "podcast" && !isPodcast),
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
                val isPodcast = mode == "podcast"
                val briefing = baseBriefing.copy(
                    mode = when {
                        isRapid -> "rapid"
                        isPodcast -> "podcast"
                        else -> "full"
                    },
                    title = when {
                        isRapid -> "Rapid Fire · Top 5 Stories"
                        isPodcast -> "Your briefing · Podcast"
                        else -> baseBriefing.title
                    },
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
