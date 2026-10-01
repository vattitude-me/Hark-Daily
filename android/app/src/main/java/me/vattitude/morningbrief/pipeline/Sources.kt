package me.vattitude.morningbrief.pipeline

/** Built-in sections and sources, mirroring app/sources.py on the server. */
data class Section(val key: String, val title: String, val emoji: String, val topic: String)

val SECTIONS = linkedMapOf(
    "canada" to Section("canada", "Canada", "🇨🇦", "the top stories from across Canada"),
    "tech" to Section("tech", "AI & Tech", "🤖", "the latest in AI and technology"),
    "custom" to Section("custom", "My Sources", "⭐", "stories from the sources you follow"),
)

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

val BUILTIN_SOURCES = listOf(
    Source(1, "CBC News · Top Stories", "https://www.cbc.ca/webfeed/rss/rss-topstories", "canada", 1.3),
    Source(2, "CBC News · Canada", "https://www.cbc.ca/webfeed/rss/rss-canada", "canada", 1.1),
    Source(3, "CBC News · Toronto", "https://www.cbc.ca/webfeed/rss/rss-canada-toronto", "canada", 0.9),
    Source(4, "Global News · Canada", "https://globalnews.ca/canada/feed/", "canada", 1.0),
    Source(5, "The Globe and Mail · Canada", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/", "canada", 1.0),
    Source(6, "National Post", "https://nationalpost.com/feed", "canada", 0.9),
    Source(7, "CityNews Toronto", "https://toronto.citynews.ca/feed/", "canada", 0.8),
    Source(8, "TechCrunch · AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "tech", 1.1),
    Source(9, "The Verge · AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "tech", 1.1),
    Source(10, "MIT Technology Review", "https://www.technologyreview.com/feed/", "tech", 1.0),
    Source(11, "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech", 0.9),
    Source(12, "VentureBeat · AI", "https://venturebeat.com/category/ai/feed/", "tech", 0.9),
    Source(13, "The Decoder", "https://the-decoder.com/feed/", "tech", 0.9),
    Source(14, "BetaKit (Canadian tech)", "https://betakit.com/feed/", "tech", 1.0),
    Source(15, "CBC · Technology & Science", "https://www.cbc.ca/webfeed/rss/rss-technology", "tech", 0.8),
    Source(16, "Hacker News · Best", "https://hnrss.org/best", "tech", 0.7),
).map { it.copy(builtin = true) }
