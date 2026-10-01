package me.vattitude.morningbrief.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FeedsTest {
    private val rss = """<?xml version="1.0"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
          <title>Circuit Report</title>
          <item>
            <title>New open-source AI model tops coding benchmark</title>
            <link>https://circuit.example/ai-model</link>
            <description>&lt;p&gt;A new model &lt;b&gt;beat&lt;/b&gt; the field.&lt;/p&gt;</description>
            <pubDate>Wed, 30 Sep 2026 10:00:00 GMT</pubDate>
            <media:content url="https://picsum.photos/600/400" medium="image"/>
          </item>
          <item>
            <title>Chip maker posts record quarter</title>
            <link>https://circuit.example/chips</link>
            <pubDate>2026-09-30T08:00:00Z</pubDate>
          </item>
        </channel></rss>"""

    @Test fun parseFeedReadsItemsImagesAndDates() {
        val (name, items) = parseFeed(rss, Source(1, "Circuit", "https://circuit.example", "tech"))
        assertEquals("Circuit Report", name)
        assertEquals(2, items.size)
        val first = items[0]
        assertTrue(first.title.startsWith("New open-source AI model"))
        assertEquals("A new model beat the field.", first.summary)
        assertTrue(first.image!!.startsWith("https://picsum.photos/"))
        assertNotNull(first.published)
        assertNotNull(items[1].published)
    }

    @Test fun atomFeedsWork() {
        val atom = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
            <entry><title>Hello world post</title><link rel="alternate" href="https://blog.example/hello"/>
            <updated>2026-09-30T08:00:00Z</updated><summary>Short.</summary></entry></feed>"""
        val (name, items) = parseFeed(atom, Source(2, "Blog", "https://blog.example", "custom"))
        assertEquals("Blog", name)
        assertEquals("https://blog.example/hello", items.single().url)
    }

    @Test fun extractPageLinksFindsHeadlines() {
        val page = """<html><body>
          <a href="/about">About us</a>
          <a href="/news/2026/09/city-council-approves-new-bike-lanes">City council approves new bike lanes on Bloor Street</a>
          <a href="/news/2026/09/local-bakery-wins-award">Local bakery wins national award for sourdough bread</a>
          <a href="https://other.com/news/x-y-z">Offsite link that should be ignored by the scraper</a>
        </body></html>"""
        val links = extractPageLinks(page, "https://local.example/news")
        assertEquals(
            listOf("City council approves new bike lanes on Bloor Street", "Local bakery wins national award for sourdough bread"),
            links.map { it.first },
        )
    }
}
