package me.vattitude.morningbrief.pipeline

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import org.jsoup.parser.Parser
import java.net.URI
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Parsing for feeds and pages (the parts of app/fetcher.py that don't touch the network). */

const val MAX_ITEMS_PER_SOURCE = 25

class FetchError(message: String) : Exception(message)

fun cleanText(raw: String?): String {
    if (raw.isNullOrBlank()) return ""
    val text = if ('<' in raw || '&' in raw) Jsoup.parse(raw).text() else raw
    return text.replace(Regex("\\s+"), " ").trim()
}

fun normalizeUrl(input: String): String {
    var url = input.trim()
    if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(url)) url = "https://$url"
    return url.substringBefore('#')
}

fun looksLikeFeed(contentType: String, body: String): Boolean {
    val head = body.take(600).trimStart().lowercase()
    return (listOf("rss", "atom", "xml").any { it in contentType } && "<html" !in head) ||
        listOf("<?xml", "<rss", "<feed", "<rdf").any { head.startsWith(it) }
}

private val RFC_DATES = listOf(
    DateTimeFormatter.RFC_1123_DATE_TIME,
    DateTimeFormatter.ofPattern("EEE, d MMM yyyy HH:mm:ss zzz", Locale.ENGLISH),
    DateTimeFormatter.ofPattern("EEE, d MMM yyyy HH:mm zzz", Locale.ENGLISH),
    DateTimeFormatter.ofPattern("d MMM yyyy HH:mm:ss Z", Locale.ENGLISH),
)

fun parseDate(raw: String?): Instant? {
    val s = raw?.trim()?.replace(Regex("\\s+"), " ") ?: return null
    if (s.isEmpty()) return null
    runCatching { return OffsetDateTime.parse(s).toInstant() }
    runCatching { return Instant.parse(s) }
    for (f in RFC_DATES) runCatching { return ZonedDateTime.parse(s, f).toInstant() }
    // "Wed, 01 Oct 2026 10:00:00 EDT" and other zone names RFC_1123 doesn't accept.
    runCatching {
        return ZonedDateTime.parse(s.replace(Regex(" (EDT|EST|CDT|CST|MDT|MST|PDT|PST)$"), " America/Toronto"),
            DateTimeFormatter.ofPattern("EEE, d MMM yyyy HH:mm:ss VV", Locale.ENGLISH)).toInstant()
    }
    return null
}

private fun Element.child(vararg names: String): Element? =
    children().firstOrNull { c -> names.any { c.tagName().equals(it, ignoreCase = true) } }

private fun Element.childText(vararg names: String): String? = child(*names)?.text()

private fun Element.childHtml(vararg names: String): String? =
    child(*names)?.let { el -> el.wholeText().ifBlank { el.html() } }

private fun entryImage(e: Element): String? {
    for (el in e.children()) {
        val tag = el.tagName().lowercase()
        if (tag == "media:content" || tag == "media:thumbnail") {
            val url = el.attr("url")
            val medium = el.attr("medium")
            val type = el.attr("type")
            if (url.isNotEmpty() && (medium.isEmpty() || medium == "image") && (type.isEmpty() || "image" in type)) return url
        }
        if (tag == "media:group") entryImage(el)?.let { return it }
        if (tag == "enclosure" && el.attr("type").startsWith("image") && el.attr("url").isNotEmpty()) return el.attr("url")
    }
    for (blob in listOf(e.childHtml("description", "summary"), e.childHtml("content:encoded", "content"))) {
        val m = Regex("<img[^>]+src=[\"']([^\"']+)[\"']").find(blob ?: continue) ?: continue
        return Parser.unescapeEntities(m.groupValues[1], true)
    }
    return null
}

private fun entryLink(e: Element): String? {
    val links = e.children().filter { it.tagName().equals("link", true) }
    // Atom: <link rel="alternate" href="..."/>; RSS: <link>url</link>
    links.firstOrNull { it.hasAttr("href") && it.attr("rel").let { r -> r.isEmpty() || r == "alternate" } }
        ?.let { return it.attr("href") }
    links.firstOrNull { it.text().isNotBlank() }?.let { return it.text().trim() }
    return e.childText("guid")?.takeIf { it.startsWith("http") }
}

/** Returns the feed's title and its items. */
fun parseFeed(body: String, source: Source): Pair<String, List<Item>> {
    val doc = Jsoup.parse(body, "", Parser.xmlParser())
    val entries = doc.getElementsByTag("item").ifEmpty { doc.getElementsByTag("entry") }
    if (entries.isEmpty() && doc.getElementsByTag("rss").isEmpty() && doc.getElementsByTag("feed").isEmpty()) {
        throw FetchError("Couldn't read that feed.")
    }
    val kept = entries.take(MAX_ITEMS_PER_SOURCE)
    val items = kept.mapIndexedNotNull { pos, e ->
        val title = cleanText(e.childText("title"))
        val link = entryLink(e)
        if (title.isEmpty() || link.isNullOrEmpty()) return@mapIndexedNotNull null
        var summary = cleanText(e.childHtml("description", "summary") ?: e.childHtml("content"))
        if (summary.length > 1200) summary = summary.take(1200).substringBeforeLast(' ') + "…"
        Item(
            title = title,
            url = link,
            sourceId = source.id,
            sourceName = source.name,
            section = source.section,
            weight = source.weight,
            published = parseDate(e.childText("pubDate", "published", "updated", "dc:date")),
            summary = summary,
            image = entryImage(e),
            position = pos,
            feedLen = kept.size,
        )
    }
    val channel = doc.getElementsByTag("channel").firstOrNull() ?: doc.getElementsByTag("feed").firstOrNull()
    val name = cleanText(channel?.child("title")?.text()).ifEmpty { runCatching { URI(source.url).host }.getOrNull() ?: "" }
    return name to items
}

fun discoverFeedLinks(doc: Document): List<String> =
    doc.select("link[rel=alternate][href]").filter {
        val type = it.attr("type").lowercase()
        "rss" in type || "atom" in type
    }.map { it.absUrl("href") }.filter { it.isNotEmpty() }

/** Heuristically find headline links on a section or home page without a feed. */
fun extractPageLinks(html: String, baseUrl: String, limit: Int = 15): List<Pair<String, String>> {
    val doc = Jsoup.parse(html, baseUrl)
    val baseHost = runCatching { URI(baseUrl).host }.getOrNull()?.removePrefix("www.") ?: ""
    val seen = mutableSetOf<String>()
    val found = mutableListOf<Pair<String, String>>()
    for (a in doc.select("a[href]")) {
        val text = a.text().replace(Regex("\\s+"), " ").trim()
        val href = a.absUrl("href").substringBefore('#')
        val uri = runCatching { URI(href) }.getOrNull() ?: continue
        val host = uri.host?.removePrefix("www.") ?: continue
        if (uri.scheme !in setOf("http", "https") || !host.endsWith(baseHost)) continue
        val words = text.split(" ").count { it.isNotEmpty() }
        val path = uri.path ?: ""
        val parts = path.split('/').filter { it.isNotEmpty() }
        // Headlines are several words long and live on deep, slug-like paths.
        if (words < 5 || words > 30 || (parts.size < 2 && '-' !in path)) continue
        if (href in seen || href.trimEnd('/') == baseUrl.trimEnd('/')) continue
        seen.add(href)
        found.add(text to href)
        if (found.size >= limit) break
    }
    return found
}
