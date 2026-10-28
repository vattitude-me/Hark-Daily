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

    private fun samplePodcastClips(hosts: String = "matthew_reference+kelly_reference"): List<JSONObject> {
        val list = mutableListOf<JSONObject>()
        list.add(
            JSONObject()
                .put("date", "2026-10-22")
                .put("hosts", hosts)
                .put("clip_key", "podcast_ready")
                .put("piece", "podcast_ready")
                .put("voice", "matthew_reference")
                .put("audio_path", "")
                .put("duration", 0.0)
                .put("text", "")
        )
        list.add(
            JSONObject()
                .put("date", "2026-10-22")
                .put("hosts", hosts)
                .put("clip_key", "pod_open_1")
                .put("piece", "pod_open_1")
                .put("voice", "matthew_reference")
                .put("audio_path", "podcast/2026-10-22/pod_open_1.mp3")
                .put("duration", 8.0)
                .put("text", "Good morning Kelly!")
        )
        list.add(
            JSONObject()
                .put("date", "2026-10-22")
                .put("hosts", hosts)
                .put("clip_key", "pod_tease_top")
                .put("piece", "pod_tease_top")
                .put("voice", "kelly_reference")
                .put("audio_path", "podcast/2026-10-22/pod_tease_top.mp3")
                .put("duration", 6.0)
                .put("text", "First up, big news in the top stories.")
        )
        list.add(
            JSONObject()
                .put("date", "2026-10-22")
                .put("hosts", hosts)
                .put("clip_key", "pod_bridge_top")
                .put("piece", "pod_bridge_top")
                .put("voice", "matthew_reference")
                .put("audio_path", "podcast/2026-10-22/pod_bridge_top.mp3")
                .put("duration", 4.0)
                .put("text", "Let's dive into the top stories.")
        )
        list.add(
            JSONObject()
                .put("date", "2026-10-22")
                .put("hosts", hosts)
                .put("clip_key", "pod_close_1")
                .put("piece", "pod_close_1")
                .put("voice", "kelly_reference")
                .put("audio_path", "podcast/2026-10-22/pod_close_1.mp3")
                .put("duration", 7.0)
                .put("text", "That's your brief for today. See you tomorrow!")
        )
        return list
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

    @Test
    fun stripHeadlineAndFillerCleansRepeatedTitleAndConnectorAndLabel() {
        val headline = "Canadian Startup Capital Association names new interim executive director"
        val script = "Canadian Startup Capital Association names new interim executive director. Taking a closer look: The news: On Thursday, the CSCA announced that Tara June (TJ) Misra had stepped into the executive director role."
        val cleaned = stripHeadlineAndFiller(headline, script)

        assertTrue(cleaned.startsWith("On Thursday, the CSCA announced"))
        assertFalse(cleaned.contains("Canadian Startup Capital"))
        assertFalse(cleaned.contains("Taking a closer look:"))
        assertFalse(cleaned.contains("The news:"))
    }

    @Test
    fun planPodcastSelectsOpenTeasersBridgesAndCloseUnderBudget() {
        val clips = samplePodcastClips()
        val plan = planPodcast(clips, listOf("top", "politics", "tech"), "2026-10-22")
        assertNotNull(plan)
        assertEquals("pod_open_1", plan!!.open.optString("clip_key"))
        assertEquals("pod_close_1", plan.close.optString("clip_key"))
        assertEquals(1, plan.teasers.size)
        assertEquals("pod_tease_top", plan.teasers[0].optString("clip_key"))
        assertEquals(1, plan.bridges.size)
        assertEquals("pod_bridge_top", plan.bridges["top"]?.optString("clip_key"))
        assertTrue(plan.banter <= 90.0)
    }

    @Test
    fun assemblePodcastBuildsTimelineWithBanterAndFallback() {
        val rows = sampleRows("c3po_reference")
        val notes = sampleNotes("c3po_reference")
        val podcastClips = samplePodcastClips()
        val stories = mapOf("top" to 3, "politics" to 2, "tech" to 2, "ai" to 2, "science" to 1, "sports" to 1)

        val podcastPack = StoryPack.assemble(
            day = "2026-10-22",
            every = rows,
            noteRows = notes,
            stories = stories,
            voice = "c3po_reference",
            sectionOrder = emptyList(),
            mode = "podcast",
            podcastClips = podcastClips,
        )

        assertNotNull(podcastPack)
        val briefing = podcastPack!!.briefing
        assertEquals("podcast", briefing.mode)
        assertTrue(briefing.isPodcast)
        assertFalse(briefing.podcastFallback)
        assertTrue(briefing.title.contains("Podcast"))
        val banterClips = podcastPack.clips.filter { it.banter }
        assertTrue(banterClips.isNotEmpty())
        assertTrue(banterClips.any { it.id == "pod_open_1" })
        assertTrue(banterClips.any { it.id == "pod_close_1" })

        val fallbackPack = StoryPack.assemble(
            day = "2026-10-22",
            every = rows,
            noteRows = notes,
            stories = stories,
            voice = "c3po_reference",
            sectionOrder = emptyList(),
            mode = "podcast",
            podcastClips = emptyList(),
        )

        assertNotNull(fallbackPack)
        assertEquals("full", fallbackPack!!.briefing.mode)
        assertFalse(fallbackPack.briefing.isPodcast)
        assertTrue(fallbackPack.briefing.podcastFallback)
        assertEquals(0, fallbackPack.clips.count { it.banter })
    }
}
