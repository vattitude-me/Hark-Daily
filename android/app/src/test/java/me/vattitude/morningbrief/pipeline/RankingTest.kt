package me.vattitude.morningbrief.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

class RankingTest {
    private fun item(title: String, section: String = "canada", source: String = "A", pos: Int = 0, hours: Long = 1) = Item(
        title = title, url = "https://x/${title.hashCode()}$source", sourceId = 1, sourceName = source, section = section,
        published = Instant.now().minus(Duration.ofHours(hours)), position = pos, feedLen = 5,
    )

    private fun filler(n: Int, section: String = "tech") =
        (0 until n).map { k -> item("Topic$k update on item$k from place$k", section, "F$k", pos = 4) }

    @Test fun mergesSameStoryFromTwoOutlets() {
        val items = listOf(
            item("Bank of Canada holds key interest rate steady at 2.5 per cent", source = "Maple"),
            item("Bank of Canada leaves interest rate unchanged as inflation cools", source = "Northern", pos = 1),
            item("Blue Jays clinch playoff spot with walk-off win", source = "Maple", pos = 2),
        )
        val picked = selectTop(items, mapOf("canada" to 5)).getValue("canada")
        assertTrue("Bank of Canada" in picked[0].lead.title)
        assertEquals(setOf("Maple", "Northern"), picked[0].sources.toSet())
        assertEquals(2, picked.size)
    }

    @Test fun mergesDifferentlyWordedHeadlinesAboutTheSameRareNames() {
        val items = listOf(
            item("Google announces Gemini 4 Argon AI model, but you can't use it yet", "tech", "Ars"),
            item("Google announces Gemini 4 and says it's so capable that only trusted cyber defenders can have it", "tech", "Verge"),
            item("Gemini 4 Argon", "tech", "HN"),
            item("Sam Altman says OpenAI won't go public until its models are safe", "tech", "Verge"),
            item("Why is Sam Altman a free man?", "tech", "HN"),
            item("Google tests a new Pixel feature for photos", "tech", "Ars"),
        ) + filler(60)
        val picked = selectTop(items, mapOf("tech" to 70)).getValue("tech")
        val gemini = picked.filter { "Gemini" in it.lead.title }
        assertEquals(1, gemini.size)
        assertEquals(setOf("Ars", "Verge", "HN"), gemini[0].sources.toSet())
        assertEquals("a shared name alone isn't the same story", 2, picked.count { "Altman" in it.lead.title })
        assertTrue(picked.any { "Pixel" in it.lead.title })
    }

    @Test fun skipsStoriesAlreadyHeard() {
        val told = item("Saskatchewan mayor stepping down now that Queen of Canada cult is gone", source = "CBC")
        val items = listOf(
            told,
            item("Saskatchewan mayor who clashed with Queen of Canada cult to step down", source = "Globe"),
            item("Minimum wage hike is now in effect across five provinces", source = "Globe", pos = 1),
            item("Province names new health minister", source = "CBC", pos = 2),
        )
        val heard = listOf(Heard("https://elsewhere/1", "Minimum wage hikes set to begin across five provinces", listOf(told.url)))
        val picked = selectTop(items, mapOf("canada" to 5), heard = heard).getValue("canada")
        assertEquals(listOf("Province names new health minister"), picked.map { it.lead.title })
    }

    @Test fun prefersAiAndDropsStaleAndDeals() {
        val items = listOf(
            item("Best laptop deals this week: 30% off", "tech", pos = 0),
            item("New AI model tops coding benchmark", "tech", pos = 3),
            item("Ancient story about phones", "tech", pos = 0, hours = 100),
        )
        val picked = selectTop(items, mapOf("tech" to 3)).getValue("tech")
        assertTrue(picked[0].lead.title.startsWith("New AI model"))
        assertTrue(picked.none { "Ancient" in it.lead.title })
    }

    @Test fun tokensIgnoreStopwords() {
        assertEquals(setOf("bank", "canada", "hold", "rate"), tokens("The Bank of Canada holds rates"))
    }

    @Test fun sectionsComeBackInOrder() {
        val items = listOf(item("Tech news about chips", "tech"), item("Canadian news about lakes", "canada"))
        assertEquals(listOf("canada", "tech"), selectTop(items, linkedMapOf("canada" to 2, "tech" to 2, "custom" to 2)).keys.toList())
    }
}
