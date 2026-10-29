package me.vattitude.morningbrief;

import static org.junit.Assert.*;

import org.junit.Test;

public class HarkShellTest {
    @Test
    public void testConstants() {
        assertEquals("hark_daily_briefing", MainActivity.BRIEFING_CHANNEL_ID);
        assertEquals("hark_playback_channel", HarkMediaService.PLAYBACK_CHANNEL_ID);
        assertEquals(2001, HarkMediaService.NOTIFICATION_ID);
        assertEquals("me.vattitude.morningbrief.START_PLAYBACK", HarkMediaService.ACTION_START_PLAYBACK);
        assertEquals("me.vattitude.morningbrief.STOP_PLAYBACK", HarkMediaService.ACTION_STOP_PLAYBACK);
    }
}
