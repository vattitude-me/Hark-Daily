package me.vattitude.morningbrief;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class DailyBriefingWorkerTest {
    @Test
    public void topSectionForEditionMapsAllSupportedEditions() {
        assertEquals("top", DailyBriefingWorker.topSectionForEdition("ca"));
        assertEquals("top_us", DailyBriefingWorker.topSectionForEdition("us"));
        assertEquals("top_in", DailyBriefingWorker.topSectionForEdition("in"));
        assertEquals("top", DailyBriefingWorker.topSectionForEdition(null));
    }

    @Test
    public void hasNonEmptyJsonArrayDetectsReadyRowsCleanly() {
        assertTrue(DailyBriefingWorker.hasNonEmptyJsonArray("[{\"date\":\"2026-11-20\"}]"));
        assertFalse(DailyBriefingWorker.hasNonEmptyJsonArray("[]"));
        assertFalse(DailyBriefingWorker.hasNonEmptyJsonArray(""));
        assertFalse(DailyBriefingWorker.hasNonEmptyJsonArray(null));
    }

    @Test
    public void extractLeadTitleReturnsHeadlineOrCleanFallback() {
        assertEquals(
            "Markets open \"higher\" on strong jobs data",
            DailyBriefingWorker.extractLeadTitle("[{\"title\":\"Markets open \\\"higher\\\" on strong jobs data\"}]")
        );
        assertEquals("Tap to listen to today's morning episode.", DailyBriefingWorker.extractLeadTitle("[]"));
        assertEquals("Tap to listen to today's morning episode.", DailyBriefingWorker.extractLeadTitle(null));
    }

    @Test
    public void torontoTodayFormatsIsoDate() {
        String today = DailyBriefingWorker.torontoToday();
        assertTrue(today.matches("\\d{4}-\\d{2}-\\d{2}"));
    }
}
