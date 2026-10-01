package me.vattitude.morningbrief.pipeline

import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import kotlin.math.ln
import kotlin.math.max

/** A port of app/ranking.py: group duplicate headlines across outlets and pick the day's top stories. */

data class Item(
    val title: String,
    val url: String,
    val sourceId: Long,
    val sourceName: String,
    val section: String,
    val weight: Double = 1.0,
    val published: Instant? = null,
    var summary: String = "",
    var image: String? = null,
    val position: Int = 0,
    val feedLen: Int = 1,
    var text: String = "",
    val kind: String = "feed",
) {
    val id: String get() = sha1(url).take(12)
}

class Story(var lead: Item, val items: MutableList<Item> = mutableListOf(lead), var score: Double = 0.0) {
    val id: String get() = lead.id
    val sources: List<String> get() = items.map { it.sourceName }.distinct()
}

/** A card from an earlier briefing: its stories aren't told again. */
data class Heard(val url: String?, val title: String, val links: List<String>)

fun sha1(text: String): String =
    MessageDigest.getInstance("SHA-1").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }

val STOPWORDS = """
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers him his how i
if in into is it its itself just me more most my new no nor not now of off on once only or other our out over own
said same says she should so some such than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your amid after over
report reports news live update updates video watch says year years day week today per cent percent
""".trim().split(Regex("\\s+")).toSet()

private val AI_TERMS = Regex(
    "\\b(ai|a\\.i\\.|artificial intelligence|openai|anthropic|claude|chatgpt|gpt[- ]?\\d*|gemini|llm|llms|deepmind|" +
        "machine learning|neural|nvidia|agent|agents|chatbot|copilot|mistral|cohere|llama|robot|robotics|model|models)\\b",
    RegexOption.IGNORE_CASE,
)
private val LOW_VALUE = Regex(
    "(\\bdeals?\\b|% off|\\bsale\\b|\\bcoupon|best .* (to buy|of 20\\d\\d)|\\bgift guide|\\bhands-on\\b|\\breview:|" +
        "\\bpodcast\\b|\\bnewsletter\\b|\\bsponsored\\b|\\bhoroscope)",
    RegexOption.IGNORE_CASE,
)
private val MAX_AGE: Duration = Duration.ofHours(48)
private val WORD = Regex("[a-z0-9']+")

fun tokens(title: String): Set<String> {
    val out = mutableSetOf<String>()
    for (raw in WORD.findAll(title.lowercase())) {
        var w = raw.value.trim('\'')
        if (w.length < 3 || w in STOPWORDS) continue
        if (w.endsWith("'s")) w = w.dropLast(2)
        else if (w.length > 4 && w.endsWith("s") && !w.endsWith("ss")) w = w.dropLast(1)
        out.add(w)
    }
    return out
}

/** How often each headline word turns up in today's pool: rare words (names, places) mark a story. */
class Rarity(titles: List<Set<String>>) {
    private val n = titles.size
    private val df = HashMap<String, Int>()
    private val cutoff: Double

    init {
        for (toks in titles) for (w in toks) df[w] = (df[w] ?: 0) + 1
        cutoff = max(3.0, 0.03 * n)
    }

    fun rare(word: String) = (df[word] ?: 0) <= cutoff
    fun weight(words: Set<String>) = words.sumOf { ln(max(n, 1).toDouble() / (df[it] ?: 1)) }
}

fun similar(a: Set<String>, b: Set<String>, rarity: Rarity? = null): Boolean {
    if (a.isEmpty() || b.isEmpty()) return false
    val common = a intersect b
    val shared = common.size
    if (shared.toDouble() / (a union b).size >= 0.4 ||
        (shared >= 3 && shared.toDouble() / minOf(a.size, b.size) >= 0.5)
    ) return true
    if (rarity == null || shared < 2) return false
    val rare = common.count { rarity.rare(it) }
    // "Gemini 4 Argon" inside "Google releases Gemini 4 Argon, its most powerful model yet"
    val smallerSet = if (a.size <= b.size) a else b
    if (common == smallerSet && rare == shared) return true
    // Different wording around the same rare names.
    val smaller = minOf(rarity.weight(a), rarity.weight(b))
    return shared >= 3 && rare >= 2 && smaller > 0 && rarity.weight(common) / smaller >= 0.3
}

fun itemScore(item: Item, now: Instant): Double {
    val position = 1 - item.position.toDouble() / max(item.feedLen, 1)
    val recency = item.published?.let {
        val hours = max(Duration.between(it, now).seconds / 3600.0, 0.0)
        max(0.0, 1 - hours / 36)
    } ?: 0.5
    var score = item.weight * (1 + 1.2 * position + 1.0 * recency)
    if (item.section == "tech" && AI_TERMS.containsMatchIn(item.title)) score += 0.6
    if (item.image != null) score += 0.1
    if (item.kind == "article") score += 10 // a link the user added by hand always makes the cut
    return score
}

fun cluster(items: List<Item>, now: Instant, rarity: Rarity? = null): List<Story> {
    val scored = items.sortedByDescending { itemScore(it, now) }
    val stories = mutableListOf<Pair<MutableList<Set<String>>, Story>>()
    val seenUrls = mutableSetOf<String>()
    for (item in scored) {
        if (!seenUrls.add(item.url)) continue
        val toks = tokens(item.title)
        val matches = stories.filter { (ts, _) -> ts.any { similar(toks, it, rarity) } }
        if (matches.isEmpty()) {
            stories.add(mutableListOf(toks) to Story(item, score = itemScore(item, now)))
            continue
        }
        // An item that matches two stories shows they are one: fold the later into the first.
        val (storyToks, story) = matches.first()
        storyToks.add(toks)
        story.items.add(item)
        for ((otherToks, other) in matches.drop(1)) {
            storyToks.addAll(otherToks)
            story.items.addAll(other.items)
        }
        if (matches.size > 1) {
            val folded = matches.drop(1).map { it.second }.toSet()
            stories.removeAll { it.second in folded }
        }
    }
    for ((_, story) in stories) {
        story.score += 0.8 * (story.sources.size - 1)
        // Prefer the version with an image and the richest summary as the card's lead.
        story.lead = story.items.maxWith(
            compareBy<Item>({ it.image != null }, { it.summary.length }, { -it.position }),
        )
    }
    return stories.map { it.second }.sortedByDescending { it.score }
}

/** [heard] holds cards from the user's recent briefings; those stories aren't told again. */
fun selectTop(
    items: List<Item>,
    limits: Map<String, Int>,
    now: Instant = Instant.now(),
    heard: List<Heard> = emptyList(),
): LinkedHashMap<String, List<Story>> {
    val fresh = items.filter {
        (it.published == null || Duration.between(it.published, now) <= MAX_AGE) && !LOW_VALUE.containsMatchIn(it.title)
    }
    val rarity = Rarity(fresh.map { tokens(it.title) })
    val heardUrls = heard.flatMap { h -> h.links.ifEmpty { listOfNotNull(h.url) } }.toSet()
    val heardToks = heard.map { tokens(it.title) }.filter { it.isNotEmpty() }
    val picked = HashMap<String, List<Story>>()
    val taken = mutableListOf<Set<String>>() // the same story can surface in two sections; tell it once
    // Hand-picked sources claim their stories first, so a duplicate elsewhere is the one dropped.
    for (section in limits.keys.sortedBy { it != "custom" }) {
        val limit = limits[section] ?: 0
        if (limit <= 0) continue
        val chosen = mutableListOf<Story>()
        for (story in cluster(fresh.filter { it.section == section }, now, rarity)) {
            val toks = tokens(story.lead.title)
            if (taken.any { similar(toks, it, rarity) }) continue
            if (story.lead.kind != "article" && (
                    story.items.any { it.url in heardUrls } ||
                        story.items.any { i -> heardToks.any { similar(tokens(i.title), it) } }
                    )
            ) continue
            taken.add(toks)
            chosen.add(story)
            if (chosen.size == limit) break
        }
        if (chosen.isNotEmpty()) picked[section] = chosen
    }
    return LinkedHashMap<String, List<Story>>().apply {
        for (k in limits.keys) picked[k]?.let { put(k, it) }
    }
}
