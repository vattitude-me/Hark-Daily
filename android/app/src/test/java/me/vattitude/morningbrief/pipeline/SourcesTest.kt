package me.vattitude.morningbrief.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SourcesTest {
    @Test fun everyCategoryHasFiveSources() {
        for (s in SECTIONS.values.filter { it.isCategory }) {
            assertEquals(s.key, 5, BUILTIN_SOURCES.count { it.section == s.key })
        }
        assertEquals(BUILTIN_SOURCES.size, BUILTIN_SOURCES.map { it.url }.toSet().size)
        assertEquals(setOf<String>(), DEFAULT_STORIES.filterValues { it > 0 }.keys)
    }

    @Test fun localNewsUsesCityOutletsAndGoogleForAnywhere() {
        val toronto = localSources("Mississauga, Ontario")
        assertTrue(toronto.size > 1)
        assertTrue(toronto.all { it.section == "local" && it.builtin })
        assertTrue(toronto.last().url.contains("/geo/Mississauga?"))
        val elsewhere = localSources("Red Deer")
        assertEquals(1, elsewhere.size)
        assertTrue(elsewhere[0].url.contains("/geo/Red%20Deer?"))
        assertTrue(localSources(" ").isEmpty())
    }

    @Test fun followIsANewsSearch() {
        val url = followUrl("Connor McDavid")
        assertTrue(url.startsWith("https://news.google.com/rss/search?q=Connor+McDavid"))
        assertTrue(isFollowUrl(url))
        assertTrue(!isFollowUrl("https://www.cbc.ca/sports"))
    }

    @Test fun localLeadNamesTheCity() {
        assertTrue(sectionLeads(listOf("local"), "Toronto, Ontario").getValue("local").contains("Toronto"))
    }

    @Test fun googleNewsCreditsTheOutlet() {
        val rss = """<rss><channel><title>Google News</title><item>
            <title>McDavid scores twice in win - Sportsnet</title>
            <link>https://news.google.com/rss/articles/CBMiabc?oc=5</link>
            <description>&lt;a href="x"&gt;McDavid scores twice in win&lt;/a&gt;</description>
            <source url="https://www.sportsnet.ca">Sportsnet</source>
            </item></channel></rss>"""
        val (_, items) = parseFeed(rss, Source(1, "Connor McDavid", followUrl("Connor McDavid"), "follow"))
        assertEquals("McDavid scores twice in win", items[0].title)
        assertEquals("Sportsnet", items[0].sourceName)
        assertEquals("", items[0].summary)
    }

    @Test fun freshInstallStartsWithNothingOn() {
        assertTrue(DEFAULT_STORIES.values.all { it == 0 })
        assertTrue(DEFAULT_STORIES.keys.containsAll(SECTIONS.keys))
    }

    @Test fun quickMixFillsTheBudgetExactly() {
        assertEquals(STORY_BUDGET, QUICK_MIX.values.sum())
        val fitted = fitBudget(QUICK_MIX)
        assertEquals(STORY_BUDGET, fitted.values.sum())
        for ((k, v) in QUICK_MIX) assertEquals(v, fitted[k])
        assertEquals(0, picksCount(fitted))
    }

    @Test fun oldCountsAreTrimmedToTheBudget() {
        val fitted = fitBudget(mapOf("canada" to 6, "tech" to 6, "world" to 3, "follow" to 3, "custom" to 4))
        assertTrue(fitted.values.sum() <= STORY_BUDGET)
        assertTrue(fitted.filterKeys { it !in PICKS }.values.all { it <= MAX_PER_SECTION })
        assertTrue(picksCount(fitted) <= MAX_PER_SECTION)
        assertEquals(STORY_BUDGET, fitted.values.sum())
        assertEquals(mapOf("follow" to 1, "custom" to 2), withPicks(emptyMap(), 3))
    }

    @Test fun aFullBriefIsAboutFiveMinutes() {
        assertEquals(5, briefMinutes(STORY_BUDGET))
        assertEquals(2, briefMinutes(4))
    }
}
