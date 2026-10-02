package me.vattitude.morningbrief.pipeline

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TextTest {
    private val article = "The Bank of Canada kept its benchmark rate at 2.5 per cent on Wednesday. " +
        "Governor Tiff Macklem said inflation has cooled but remains above target in several regions. " +
        "Economists had widely expected the hold after a run of mixed economic data. " +
        "Markets barely moved on the news. Some analysts now expect a cut early next year if job growth slows. " +
        "The next decision is due in six weeks."

    @Test fun summarizePrefersLeadAndRespectsLength() {
        val summary = summarize(article, maxWords = 60)
        assertTrue(summary, summary.startsWith("The Bank of Canada kept its benchmark rate"))
        assertTrue(summary.split(" ").size <= 61)
        assertEquals("Short fallback text.", summarize("", fallback = "Short fallback text."))
    }

    @Test fun speakableExpandsSymbolsForTheVoice() {
        val out = speakable("Startup raises \$120M (Series B) — up 30% vs. last year 🚀 https://x.co/a")
        assertTrue(out, "120 million dollars" in out)
        assertTrue(out, "30 percent" in out)
        assertTrue(out, "versus" in out)
        assertFalse(out, "http" in out || "🚀" in out || "(" in out)
        assertTrue(speakable("C\$2.5 billion deal").startsWith("2.5 billion Canadian dollars"))
    }

    @Test fun siteFurnitureIsDropped() {
        val text = "Posts from this author will be added to your daily email digest and your homepage feed.\n" +
            "Apple released a phone today with a bigger battery, the company said.\n" +
            "Follow topics and authors from this story to see more like this in your personalized homepage feed.\n" +
            "Sign up for our newsletter"
        assertEquals("Apple released a phone today with a bigger battery, the company said.", dropBoilerplate(text))
    }
}
