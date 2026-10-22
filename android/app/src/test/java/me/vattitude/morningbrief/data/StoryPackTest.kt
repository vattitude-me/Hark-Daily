package me.vattitude.morningbrief.data

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class StoryPackTest {
    private fun sampleRows(voice: String = "c3po_reference"): List<JSONObject> {
        val rows = mutableListOf<JSONObject>()
        val sections = listOf("top", "politics", "tech", "ai", "science", "sports")
        for (section in sections) {
            for (rank in 1..3) {
                rows.add(
                    JSONObject()
                        .put("date", "2026-10-22")
                        .put("section", section)
                        .put("rank", rank)
                        .put("voice", "her_reference")
                        .put("headline", "Headline $section $rank")
                        .put("script", "Summary for $section story $rank")
                        .put("url", "https://example.com/$section/$rank")
                        .put("source_name", "The Guardian")
                        .put("audio_path", "pack/2026-10-22/her_reference/$section-$rank.mp3")
                        .put("duration", 10.0)
                )
                rows.add(
                    JSONObject()
                        .put("date", "2026-10-22")
                        .put("section", section)
                        .put("rank", rank)
                        .put("voice", voice)
                        .put("headline", "Headline $section $rank")
                        .put("script", "Summary for $section story $rank")
                        .put("url", "https://example.com/$section/$rank")
                        .put("source_name", "The Guardian")
                        .put("audio_path", "pack/2026-10-22/$voice/$section-$rank.mp3")
                        .put("duration", 12.0)
                )
            }
        }
        return rows
    }

    private fun sampleNotes(voice: String = "c3po_reference"): List<JSONObject> {
        val notes = mutableListOf<JSONObject>()
        val keys = listOf(
            "greeting_morning" to "Good morning!",
            "rapid_intro" to "Here is your Rapid Fire update.",
            "outro" to "Have a great day.",
            "section_top" to "Starting with top stories.",
            "section_politics" to "In politics.",
            "section_tech" to "Moving to tech.",
            "section_ai" to "Now in AI.",
            "section_science" to "In science.",
            "section_sports" to "And in sports.",
        )
        for ((k, text) in keys) {
            notes.add(
                JSONObject()
                    .put("date", "2026-10-22")
                    .put("voice", voice)
                    .put("note_key", k)
                    .put("text", text)
                    .put("audio_path", "notes/2026-10-22/$voice/$k.mp3")
                    .put("duration", 2.5)
            )
        }
        return notes
    }

    @Test
    fun assembleFullAndRapidBuildsDistinctPacksWithAllSections() {
        val rows = sampleRows("c3po_reference")
        val notes = sampleNotes("c3po_reference")
        val stories = mapOf("top" to 3, "politics" to 2, "tech" to 2, "ai" to 2, "science" to 1, "sports" to 1)

        val full = StoryPack.assemble(
            day = "2026-10-22",
            every = rows,
            noteRows = notes,
            stories = stories,
            voice = "c3po_reference",
            sectionOrder = emptyList(),
            mode = "full",
        )
        val rapid = StoryPack.assemble(
            day = "2026-10-22",
            every = rows,
            noteRows = notes,
            stories = stories,
            voice = "c3po_reference",
            sectionOrder = emptyList(),
            mode = "rapid",
        )

        assertNotNull(full)
        assertNotNull(rapid)

        assertEquals("full", full!!.briefing.mode)
        assertFalse(full.briefing.isRapid)
        assertEquals(11, full.briefing.cards.size)
        assertTrue(full.briefing.sections.size >= 5)

        assertEquals("rapid", rapid!!.briefing.mode)
        assertTrue(rapid.briefing.isRapid)
        assertEquals(5, rapid.briefing.cards.size)
        assertTrue(rapid.briefing.title.contains("Rapid Fire"))
        assertTrue(full.briefing.mediaId != rapid.briefing.mediaId)
    }

    @Test
    fun lineupFallsBackToDefaultsWhenAllZero() {
        val zeroed = mapOf("top" to 0, "tech" to 0)
        val result = lineup(zeroed)
        assertTrue(result.isNotEmpty())
        assertTrue((result["top"] ?: 0) > 0)
    }
}
