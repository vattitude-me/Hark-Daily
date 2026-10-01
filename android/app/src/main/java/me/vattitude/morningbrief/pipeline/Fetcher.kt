package me.vattitude.morningbrief.pipeline

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import net.dankito.readability4j.Readability4J
import okhttp3.OkHttpClient
import okhttp3.Request
import org.jsoup.Jsoup
import java.io.IOException
import java.net.URI
import java.time.Instant
import java.util.concurrent.TimeUnit

/** Network side of app/fetcher.py: feeds, pages and single articles, fetched in parallel. */

private const val USER_AGENT =
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36 MorningBrief/2.0"
private val FEED_PATHS = listOf("feed", "rss", "feed.xml")

data class Page(val url: String, val contentType: String, val body: String)

data class Article(
    val title: String?,
    val description: String?,
    val image: String?,
    val siteName: String?,
    val text: String,
    val isArticle: Boolean,
)

data class Detection(val kind: String, val feedUrl: String?, val name: String, val sample: List<String>)

class Fetcher(timeoutSeconds: Long = 20) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .callTimeout(timeoutSeconds + 10, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    suspend fun get(url: String): Page = withContext(Dispatchers.IO) {
        val uri = runCatching { URI(url) }.getOrNull()
        if (uri?.scheme !in setOf("http", "https") || uri?.host.isNullOrEmpty()) throw FetchError("Only http(s) links are supported.")
        val host = uri!!.host
        val request = Request.Builder().url(url)
            .header("User-Agent", USER_AGENT)
            .header("Accept-Language", "en-CA,en;q=0.9")
            .build()
        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code >= 400) throw FetchError("$host returned HTTP ${resp.code}")
                val body = resp.body?.string() ?: ""
                Page(resp.request.url.toString(), resp.header("Content-Type")?.lowercase() ?: "", body)
            }
        } catch (e: IOException) {
            throw FetchError("Couldn't reach $host: ${e.javaClass.simpleName}")
        }
    }

    suspend fun fetchSource(source: Source): List<Item> {
        when (source.kind) {
            "feed" -> {
                val page = get(source.feedUrl ?: source.url)
                return withContext(Dispatchers.Default) { parseFeed(page.body, source).second }
            }
            "article" -> {
                val page = get(source.url)
                val art = withContext(Dispatchers.Default) { extractArticle(page.body, page.url) }
                return listOf(
                    Item(
                        title = cleanText(art.title).ifEmpty { source.name },
                        url = page.url,
                        sourceId = source.id,
                        sourceName = cleanText(art.siteName).ifEmpty { source.name },
                        section = source.section,
                        weight = source.weight,
                        summary = cleanText(art.description),
                        image = art.image,
                        text = art.text,
                        kind = "article",
                        published = Instant.now(),
                    ),
                )
            }
            else -> {
                val page = get(source.url)
                val links = withContext(Dispatchers.Default) { extractPageLinks(page.body, page.url) }
                return links.mapIndexed { pos, (title, href) ->
                    Item(title, href, source.id, source.name, source.section, source.weight,
                        position = pos, feedLen = links.size, kind = "page")
                }
            }
        }
    }

    /** Fetch every source; returns items plus a per-source status ("ok" or the problem). */
    suspend fun fetchAll(sources: List<Source>, concurrency: Int = 8): Pair<List<Item>, Map<Long, String>> = coroutineScope {
        val sem = Semaphore(concurrency)
        val results = sources.map { src ->
            async {
                sem.withPermit {
                    try {
                        src.id to (fetchSource(src) to "ok")
                    } catch (e: Exception) { // one bad source mustn't sink the briefing
                        src.id to (emptyList<Item>() to (if (e is FetchError) e.message!! else "error: ${e.javaClass.simpleName}"))
                    }
                }
            }
        }.awaitAll()
        results.flatMap { it.second.first } to results.associate { it.first to it.second.second }
    }

    /** Download full article text and a lead image for the stories that made the cut. */
    suspend fun enrich(items: List<Item>, concurrency: Int = 6) = coroutineScope {
        val sem = Semaphore(concurrency)
        items.map { item ->
            async {
                if (item.text.isNotEmpty() && item.image != null) return@async
                val art = sem.withPermit {
                    runCatching {
                        val page = get(item.url)
                        withContext(Dispatchers.Default) { extractArticle(page.body, page.url) }
                    }.getOrNull()
                } ?: return@async
                if (art.text.length > item.text.length) item.text = art.text
                if (item.image == null) item.image = art.image
                if (item.summary.isEmpty()) item.summary = cleanText(art.description)
            }
        }.awaitAll()
    }

    /** Work out what a user-supplied link is: a feed, a site with a feed, a page or an article. */
    suspend fun detect(input: String): Detection {
        val url = normalizeUrl(input)
        val page = get(url)
        val probe = Source(0, "", page.url, "custom")
        if (looksLikeFeed(page.contentType, page.body)) {
            val (name, items) = parseFeed(page.body, probe)
            return Detection("feed", page.url, name, items.take(4).map { it.title })
        }
        val doc = Jsoup.parse(page.body, page.url)
        val candidates = discoverFeedLinks(doc).toMutableList()
        val uri = URI(page.url)
        val shallow = (uri.path ?: "").split('/').count { it.isNotEmpty() } <= 2
        if (shallow) {
            val base = if (page.url.endsWith("/")) page.url else "${page.url}/"
            candidates += FEED_PATHS.map { base + it }
        }
        for (cand in candidates.distinct()) {
            val fp = runCatching { get(cand) }.getOrNull() ?: continue
            if (!looksLikeFeed(fp.contentType, fp.body)) continue
            val (name, items) = runCatching { parseFeed(fp.body, probe) }.getOrNull() ?: continue
            if (items.isNotEmpty()) return Detection("feed", fp.url, name, items.take(4).map { it.title })
        }
        val art = extractArticle(page.body, page.url)
        val site = cleanText(art.siteName).ifEmpty { uri.host?.removePrefix("www.") ?: "" }
        val links = extractPageLinks(page.body, page.url)
        val slug = (uri.path ?: "").trimEnd('/').substringAfterLast('/')
        val hint = art.isArticle || slug.count { it == '-' } >= 3 || !shallow
        if ((art.text.length > 400 && hint) || (art.text.length > 1200 && links.size < 5)) {
            val title = cleanText(art.title).ifEmpty { site }
            return Detection("article", null, title, listOf(title))
        }
        if (links.isNotEmpty()) return Detection("page", null, site, links.take(4).map { it.first })
        throw FetchError("Couldn't find any news on that page. Try the site's RSS feed or an article link.")
    }
}

fun extractArticle(html: String, url: String): Article {
    val doc = Jsoup.parse(html, url)
    fun meta(vararg keys: String) = keys.firstNotNullOfOrNull { k ->
        doc.selectFirst("meta[property=$k], meta[name=$k]")?.attr("content")?.takeIf { it.isNotBlank() }
    }
    val image = meta("og:image", "twitter:image")?.let { img ->
        runCatching { URI(url).resolve(img).toString() }.getOrNull()
    }?.takeIf { it.startsWith("http") }
    val text = runCatching {
        val parsed = Readability4J(url, html).parse()
        val content = parsed.articleContent
        val lines = content?.select("p, h1, h2, h3, h4, li:not(:has(p)), blockquote:not(:has(p))")
            ?.map { it.text().trim() }?.filter { it.isNotEmpty() }
        if (lines.isNullOrEmpty()) parsed.textContent?.trim() ?: "" else lines.joinToString("\n")
    }.getOrDefault("")
    return Article(
        title = meta("og:title", "twitter:title") ?: doc.title(),
        description = meta("og:description", "description", "twitter:description"),
        image = image,
        siteName = meta("og:site_name"),
        text = text,
        isArticle = meta("og:type") == "article",
    )
}
