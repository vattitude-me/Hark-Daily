package me.vattitude.morningbrief.pipeline

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.time.ZonedDateTime
import java.time.format.TextStyle
import java.util.Locale
import java.util.concurrent.TimeUnit

/** A port of app/writer.py: card copy and the spoken script. */

data class StoryCopy(val headline: String, val summary: String, val spoken: String, val writer: String = "built-in")

data class Script(
    val intro: String,
    val sectionLeads: Map<String, String>,
    val stories: Map<String, StoryCopy>,
    val outro: String,
    val writer: String,
)

private val CONNECTORS = listOf("", "Next,", "Meanwhile,", "Also today,", "In other news,", "Elsewhere,", "And")
private val CREDITS = listOf("That's from %s.", "Via %s.", "%s has the full story.", "Reporting from %s.")

/** Stable per story, so the same story sounds the same in every briefing. */
private fun pick(story: Story, size: Int) = (story.id.toLong(16) % size).toInt()

private fun sourcePhrase(story: Story): String {
    val names = story.sources
    return if (names.size >= 3) "${names[0]}, ${names[1]} and others" else names.joinToString(" and ")
}

fun credit(story: Story) = CREDITS[pick(story, CREDITS.size)].format(sourcePhrase(story))

fun templateCopy(story: Story): StoryCopy {
    val lead = story.lead
    val summary = summarize(lead.text, fallback = lead.summary, maxWords = 60, title = lead.title)
        .ifEmpty { lead.summary }.ifEmpty { lead.title }
    var body = summarize(lead.text, fallback = lead.summary, maxWords = 55, maxSentences = 2, title = lead.title)
    if (body.endsWith("…")) {
        // Never stop mid-sentence out loud: drop the clipped tail.
        val cut = body.lastIndexOf(". ")
        body = if (cut >= 0) body.substring(0, cut + 1) else ""
    }
    val connector = CONNECTORS[pick(story, CONNECTORS.size)]
    val title = lead.title.trimEnd('.')
    val opener = if (connector.isNotEmpty()) "$connector $title." else "$title."
    return StoryCopy(lead.title, summary, "$opener\n$body".trim())
}

fun sectionLeads(sections: List<String>, city: String? = null): Map<String, String> = sections.mapIndexed { i, key ->
    val place = city?.substringBefore(',')?.trim().orEmpty().ifEmpty { "town" }
    val topic = (SECTIONS[key]?.topic ?: "news from $key").replace("{city}", place)
    key to if (sections.size == 1) topic.replaceFirstChar { it.uppercase() } + "." else {
        val opener = if (i == 0) "First" else if (i == sections.size - 1) "And finally" else "Next"
        "$opener, $topic."
    }
}.toMap()

fun spokenDate(now: ZonedDateTime): String =
    "${now.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.ENGLISH)}, " +
        "${now.month.getDisplayName(TextStyle.FULL, Locale.ENGLISH)} ${now.dayOfMonth}"

fun compose(
    picked: Map<String, List<Story>>,
    copies: Map<String, StoryCopy>,
    now: ZonedDateTime,
    weather: String?,
    name: String?,
    saySources: Boolean,
    city: String? = null,
): Script {
    val hello = if (!name.isNullOrBlank()) "Good morning, $name!" else "Good morning!"
    val intro = "$hello It's ${spokenDate(now)}. ${if (weather != null) "$weather " else ""}Here's your briefing."
    val stories = picked.values.flatten().associate { s ->
        val copy = copies.getValue(s.id)
        s.id to if (saySources) copy.copy(spoken = "${copy.spoken}\n${credit(s)}") else copy
    }
    val used = stories.values.map { it.writer }.toSet()
    val writer = if (used == setOf("built-in")) "built-in" else if ("built-in" !in used) used.first() else "mixed"
    val day = now.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.ENGLISH)
    return Script(
        intro = intro,
        sectionLeads = sectionLeads(picked.keys.toList(), city),
        stories = stories,
        outro = "That's your briefing for this $day. Have a wonderful day, and I'll talk to you tomorrow morning.",
        writer = writer,
    )
}

// ------------------------------------------------------------------ Groq
private const val SYSTEM_PROMPT = """You write copy for a warm, trustworthy morning audio news briefing for listeners in Canada.
The spoken text is read aloud by a text-to-speech voice, so it is written for the ear; the summary appears on a news card.

Return a JSON object with exactly these keys:
- "headline": a clear, neutral headline of at most 12 words.
- "summary": the card text, 40 to 60 words of plain factual prose built only from the supplied text.
- "spoken": what the host says, as an array of 2 to 4 beats, 45 to 85 words in all. The app leaves a short pause
  between beats, so each beat is one idea in one or two sentences. The first beat is the news itself, who did
  what, in one sentence; then the key detail; then why it matters or what happens next.

How the spoken beats should sound:
- Like a calm radio host talking to one listener: plain words, contractions, active voice.
- Sentences of 8 to 20 words, with the subject and verb near the start. No long lead-in clauses.
- Attribution after the fact, not before it: "The plant will close in March, the company said."
- Commas only where a speaker would breathe. No semicolons, colons, dashes, brackets or quotation marks;
  paraphrase quotes instead.
- Numbers the way people say them: rounded, at most two in a sentence, written as digits with "percent" and
  "dollars" in words (55 percent, 64 million dollars, 11 a.m.).
- Use a person's full name and role the first time, then the surname. Expand initials a listener
  might not know.
- Never name the news outlet or say "reports" or "according to" about it: the app credits the source
  separately. Start with the news itself, not a greeting or a transition: the app adds those.
- No URLs, emoji, lists or markdown.

Stay strictly factual and neutral. Never add facts that aren't in the text; if the text is thin, say less."""

/** The spoken copy as beats, one per line: the voice pauses between lines. */
fun spokenBeats(value: Any?): String {
    val beats = when (value) {
        is JSONArray -> (0 until value.length()).map { value.opt(it)?.toString() ?: "" }
        null, JSONObject.NULL -> emptyList()
        else -> value.toString().split("\n")
    }
    return beats.map { it.trim().replace(Regex("\\s+"), " ") }.filter { it.isNotEmpty() }.joinToString("\n")
}

/**
 * Writes each story's copy with the user's own Groq key when one is set, falling back to the
 * built-in template for the rest of the build after a limit or repeated failures.
 */
class StoryWriter(
    private val apiKey: String?,
    models: List<String> = listOf("openai/gpt-oss-120b", "openai/gpt-oss-20b"),
) {
    private val models = if (apiKey.isNullOrBlank()) mutableListOf() else models.toMutableList()
    private var failures = 0
    val notes = mutableListOf<String>()
    private val client = OkHttpClient.Builder().callTimeout(60, TimeUnit.SECONDS).build()

    fun copy(section: String, story: Story): StoryCopy = ai(section, story) ?: templateCopy(story)

    private fun ai(section: String, story: Story): StoryCopy? {
        while (models.isNotEmpty()) {
            val model = models.first()
            try {
                return call(model, section, story)
            } catch (e: LimitHit) {
                models.removeAt(0)
            } catch (e: Exception) {
                failures++
                if (failures >= 3) {
                    notes.add("Groq unavailable: ${e.message?.take(120)}")
                    models.clear()
                }
                return null
            }
        }
        return null
    }

    private class LimitHit(msg: String) : Exception(msg)

    private fun call(model: String, section: String, story: Story): StoryCopy {
        val lead = story.lead
        val payload = JSONObject()
            .put("section", SECTIONS[section]?.title ?: section)
            .put("headline", lead.title)
            .put("text", lead.text.ifEmpty { lead.summary }.ifEmpty { lead.title }.take(2500))
        val body = JSONObject()
            .put("model", model)
            .put("temperature", 0.4)
            .put("max_tokens", 1200)
            .put("response_format", JSONObject().put("type", "json_object"))
            .put("messages", JSONArray()
                .put(JSONObject().put("role", "system").put("content", SYSTEM_PROMPT))
                .put(JSONObject().put("role", "user").put("content", payload.toString())))
        if (model.startsWith("openai/gpt-oss")) body.put("reasoning_effort", "low")
        val request = Request.Builder().url("https://api.groq.com/openai/v1/chat/completions")
            .header("Authorization", "Bearer $apiKey")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        client.newCall(request).execute().use { resp ->
            val text = resp.body?.string() ?: ""
            when {
                resp.code == 401 || resp.code == 403 -> {
                    notes.add("Your Groq key was rejected.")
                    models.clear()
                    throw LimitHit("auth")
                }
                resp.code == 429 -> throw LimitHit("rate limited")
                (resp.code == 400 || resp.code == 404) && "model" in text.lowercase() -> throw LimitHit("model gone")
                resp.code >= 400 -> throw IllegalStateException("HTTP ${resp.code}")
            }
            val content = JSONObject(text).getJSONArray("choices").getJSONObject(0)
                .getJSONObject("message").getString("content")
            val data = JSONObject(content)
            val summary = data.optString("summary").trim()
            val spoken = spokenBeats(data.opt("spoken"))
            require(summary.isNotEmpty() && spoken.isNotEmpty()) { "empty summary or spoken text" }
            failures = 0
            return StoryCopy(data.optString("headline").trim().ifEmpty { lead.title }, summary, spoken, model)
        }
    }
}
