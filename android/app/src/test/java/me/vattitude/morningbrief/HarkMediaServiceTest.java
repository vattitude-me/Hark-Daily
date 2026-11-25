package me.vattitude.morningbrief;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class HarkMediaServiceTest {
    @Test
    public void normalizeArtworkUrlAcceptsPublicHttpsUrlsAndCdnPaths() {
        assertEquals(
            "https://i.cbc.ca/ais/d00da2e6-a84c-4e38-8070-520079d8f612,1795461725211/full/max/0/default",
            HarkMediaService.normalizeArtworkUrl(
                "  https://i.cbc.ca/ais/d00da2e6-a84c-4e38-8070-520079d8f612,1795461725211/full/max/0/default  "
            )
        );
        assertEquals(
            "https://techcrunch.com/wp-content/uploads/2026/10/hero.jpg?resize=1200,800",
            HarkMediaService.normalizeArtworkUrl("https://techcrunch.com/wp-content/uploads/2026/10/hero.jpg?resize=1200,800")
        );
        assertEquals(
            "https://www.sciencedaily.com/images/1920/wreck.webp",
            HarkMediaService.normalizeArtworkUrl("https://www.sciencedaily.com/images/1920/wreck.webp")
        );
    }

    @Test
    public void normalizeArtworkUrlRejectsUnsafeOrUnsupportedUrls() {
        assertNull(HarkMediaService.normalizeArtworkUrl(null));
        assertNull(HarkMediaService.normalizeArtworkUrl(""));
        assertNull(HarkMediaService.normalizeArtworkUrl("   "));
        assertNull(HarkMediaService.normalizeArtworkUrl("http://cdn.example.com/photo.jpg"));
        assertNull(HarkMediaService.normalizeArtworkUrl("javascript:alert(1)"));
        assertNull(HarkMediaService.normalizeArtworkUrl("file:///sdcard/photo.jpg"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://hark.vattitude.ca/icons/covers/tech.svg"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://localhost/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://myhost.local/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://127.0.0.1/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://10.0.0.5/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://192.168.1.25/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://172.16.4.2/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://169.254.169.254/latest/meta-data"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://[::1]/image.png"));
        assertNull(HarkMediaService.normalizeArtworkUrl("https://[fd00::1]/image.png"));
    }

    @Test
    public void calculateInSampleSizeRespectsMaxDimension() {
        assertEquals(1, HarkMediaService.calculateInSampleSize(512, 512, 512));
        assertEquals(1, HarkMediaService.calculateInSampleSize(400, 300, 512));
        assertEquals(2, HarkMediaService.calculateInSampleSize(1024, 1024, 512));
        assertEquals(2, HarkMediaService.calculateInSampleSize(1920, 1080, 512));
        assertEquals(4, HarkMediaService.calculateInSampleSize(2400, 1600, 512));
        assertEquals(1, HarkMediaService.calculateInSampleSize(0, 0, 512));
    }
}
