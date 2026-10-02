package me.vattitude.morningbrief.pipeline

import kotlin.math.pow

/** Ports of app/summarizer.py (extractive summaries) and app/tts/text.py (text made easy to read aloud). */

private val SENTENCE_SPLIT = Regex("(?:(?<=[.!?])|(?<=[.!?][\"”’']))\\s+(?=[A-Z0-9\"“‘'])")
/** A site's own furniture, not the story: sign-up prompts, follow buttons, credits, author bios. */
private val BOILERPLATE = Regex(
    "(sign up|sign in|log in|subscribe|newsletter|click here|read more|continue reading|follow us|advertisement|" +
        "©|all rights reserved|this article|photo:|image:|getty images|the canadian press$|" +
        "posts from this|email digest|homepage feed|your feed|follow (this |the )?(author|topic|story|series)|" +
        "see all (stories|posts)|listen to this (article|story)|share (this|the) (article|story)|" +
        "we may earn|affiliate link|commission when you buy|cookie|reporting by|editing by|" +
        "this story (has been|was) (updated|originally)|^related:|^recommended:|^more:|^watch:|^read:)",
    RegexOption.IGNORE_CASE,
)

/** Drops lines of site furniture from article text, so neither the summary nor the voice reads them. */
fun dropBoilerplate(text: String): String =
    text.lines().filterNot { line ->
        val l = line.trim()
        l.split(' ').size <= 40 && BOILERPLATE.containsMatchIn(l)
    }.joinToString("\n")

private val SENTENCE_END = Regex("[.!?][\"”’']?$")
private val NON_WORD = Regex("\\W+")
private val SPACES = Regex("\\s+")
private val LETTERS = Regex("[a-z']+")

/** Split article text into sentences, skipping headings, captions and a repeated title. */
fun splitSentences(text: String, title: String = ""): List<String> {
    val out = mutableListOf<String>()
    val titleKey = title.lowercase().replace(NON_WORD, "")
    for (line in text.lines()) {
        val para = line.replace(SPACES, " ").trim()
        if (para.isEmpty()) continue
        if (titleKey.isNotEmpty() && para.lowercase().replace(NON_WORD, "") == titleKey) continue
        if (!SENTENCE_END.containsMatchIn(para) && para.split(" ").size < 20) continue // heading, byline or caption
        out.addAll(para.split(SENTENCE_SPLIT).map { it.trim() }.filter { it.isNotEmpty() })
    }
    return out
}

private fun clipWords(text: String, maxWords: Int): String {
    val words = text.split(SPACES).filter { it.isNotEmpty() }
    if (words.size <= maxWords) return text
    return words.take(maxWords).joinToString(" ").trimEnd(',', ';', ':', '—', '-') + "…"
}

private fun contentWords(s: String) =
    LETTERS.findAll(s.lowercase()).map { it.value }.filter { it !in STOPWORDS && it.length > 2 }.toList()

/** Pick the most informative sentences (term frequency with a news-lead bias). */
fun summarize(text: String, fallback: String = "", maxWords: Int = 60, maxSentences: Int = 3, title: String = ""): String {
    val sentences = splitSentences(text, title)
        .filter { it.split(" ").size in 6..50 && !BOILERPLATE.containsMatchIn(it) }
        .take(40)
    if (sentences.isEmpty()) return if (fallback.isNotBlank()) clipWords(fallback.trim(), maxWords) else ""

    val freq = HashMap<String, Int>()
    for (s in sentences) for (w in contentWords(s)) freq[w] = (freq[w] ?: 0) + 1
    val top = (freq.values.maxOrNull() ?: 1).toDouble()

    fun score(idx: Int, sent: String): Double {
        val words = contentWords(sent)
        if (words.isEmpty()) return 0.0
        val tf = words.sumOf { (freq[it] ?: 0) / top } / words.size.toDouble().pow(0.8)
        val leadBonus = if (idx == 0) 1.0 else if (idx < 3) 0.5 else 0.0
        return tf + leadBonus
    }

    val ranked = sentences.indices.sortedByDescending { score(it, sentences[it]) }
    val chosen = mutableListOf<Int>()
    var words = 0
    for (idx in ranked) {
        val n = sentences[idx].split(" ").size
        if (chosen.isNotEmpty() && words + n > maxWords) continue
        chosen.add(idx)
        words += n
        if (chosen.size >= maxSentences) break
    }
    return clipWords(chosen.sorted().joinToString(" ") { sentences[it] }, maxWords)
}

// ------------------------------------------------------------------ speakable
private val ABBREVIATIONS = listOf(
    "\\be\\.g\\." to "for example",
    "\\bi\\.e\\." to "that is",
    "\\bvs\\.?" to "versus",
    "\\bapprox\\." to "approximately",
    "\\bGov\\." to "Governor",
    "\\bSen\\." to "Senator",
    "\\bSt\\." to "Saint",
    "\\bOnt\\." to "Ontario",
    "\\bQue\\." to "Quebec",
    "\\bMt\\." to "Mount",
    "\\bNo\\. (?=\\d)" to "number ",
    "\\bCEO's\\b" to "C E O's",
).map { (p, r) -> Regex(p) to r }
private val SCALE = mapOf(
    "k" to "thousand", "m" to "million", "mn" to "million", "b" to "billion", "bn" to "billion",
    "t" to "trillion", "tn" to "trillion",
)
private val MONEY = Regex(
    "(?:\\b(C|CA|US|U\\.S\\.))?\\$\\s?(\\d[\\d,]*(?:\\.\\d+)?)(?:\\s?(thousand|million|billion|trillion)\\b|(bn|mn|tn|[kmbt])\\b)?",
    RegexOption.IGNORE_CASE,
)
private val EMOJI = Regex("[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{27BF}\\x{1F1E6}-\\x{1F1FF}\\x{200D}\\x{FE0F}]")

fun speakable(input: String): String {
    var text = input.replace(Regex("https?://\\S+"), "")
    text = text.replace(EMOJI, "")
    text = text.replace("&", " and ").replace("%", " percent").replace("…", ".")
    text = text.replace(Regex("[\u2010\u2011\u00ad]"), "-") // the hyphens models use that voices trip on
    text = text.replace(Regex("\\s*[—–]\\s*"), ", ")
    text = MONEY.replace(text) { m ->
        val prefix = m.groupValues[1]
        val currency = when (prefix.uppercase()) {
            "C", "CA" -> "Canadian dollars"
            "US", "U.S." -> "U.S. dollars"
            else -> "dollars"
        }
        val scale = m.groupValues[3].ifEmpty { SCALE[m.groupValues[4].lowercase()] ?: "" }
        listOf(m.groupValues[2], scale, currency).filter { it.isNotEmpty() }.joinToString(" ")
    }
    for ((pattern, repl) in ABBREVIATIONS) text = pattern.replace(text, Regex.escapeReplacement(repl))
    text = text.replace(Regex("\\s*[\\[\\]()]\\s*"), ", ")
    text = text.replace(Regex("[*_#|<>]"), " ")
    text = text.replace(Regex("\\s+,"), ",")
    text = text.replace(Regex(",\\s*,+"), ",")
    text = text.replace(SPACES, " ").trim(' ', ',')
    if (text.isNotEmpty() && text.last() !in ".!?") text += "."
    return text
}
