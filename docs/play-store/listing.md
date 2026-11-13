# Play Store listing

Assets in this folder: `icon-512.png` (store icon), `feature-graphic.png` (1024×500) and `screenshots/` (1080×1920,
in listing order). `icon.svg` is the source for the icon.

## Title (30 max)

Hark Daily: News Read Aloud

## Short description (80 max)

The news you hear, not just read. AI duo & neural morning news briefings.

## Full description

Wake up to the news, read aloud.

Hark Daily gathers trusted stories from regional and global publishers and turns them into a crisp audio briefing, ready before you get up. Press play over coffee, on the commute, or on a run, and hear today's headlines in minutes.

**Your news, your way**
• 8 curated topics: Top Stories, AI, Tech, Politics, Markets, Entertainment, Science, and Sports
• 3 regional editions: Canada, USA, and India — switch anytime
• Dynamic AI narrators: listen to our conversational AI Duo (Matthew & Kelly) or solo voices (Alice, Jerry, Mike, C-3PO)
• Dual listening modes: Full briefing with context or swift Rapid headline sweep
• Customize story counts, reorder topics, and prioritize your favorite feeds

**Listen and follow along**
• Smooth 3D card deck interface — swipe or tap through today's stories
• Live synced read-along teleprompter highlights every story as it plays
• Scrub waveform, skip between stories, adjust playback speed, and play in the background with lock-screen media controls
• Every story links directly to the full original article from its publisher

**Simple and transparent**
• No ads and no account required to listen to the daily briefing
• Optional Google Sign-In syncs your edition, narrator, and sources across Web and Android
• Spot a summary or pronunciation issue? Report it directly from any story card

## Category and tags

- Category: News & Magazines
- Tags: News, Audio, Podcasts

## Keywords to keep in the copy

audio news, news read aloud, daily news briefing, morning news, news podcast, text to speech news, local news, personalized news

## Data safety answers

| Data | Collected | Why | Shared |
|---|---|---|---|
| Email address | Only if you sign in | Account authentication & settings sync | No |
| Name & profile photo | Only if you sign in with Google | Account display & settings sync | No |
| App settings, topics & custom sources | Only if you sign in | Sync preferences across devices | No |
| Weather city | Entered by you; coordinates sent to Open-Meteo | Morning weather forecast | No |
| Summary or audio reports | Only when submitted: story headline, reason, optional note & app version | Fixing summaries and pronunciation | No |
| Usage analytics | Aggregate page views, search queries & playback events (GA4 with IP anonymization, consent-gated) | Performance & feature diagnostics | Analytics processor (anonymized, never sold) |

No device location permission, no advertising ID. All data is encrypted in transit (HTTPS). Signed-in users can permanently delete their account and synced data anytime under **Settings → Delete account** (also available via web).

## Play Console App Content Declarations

- **News App Declaration**: Yes — Hark Daily aggregates public RSS/news feeds (CBC News, TechCrunch, BetaKit, BBC, Reuters/market feeds, and publisher outlets), attributes every story to its original publisher with direct outbound article links, and is owned/maintained at `https://vattitude.ca` (`https://hark.vattitude.ca`).
- **Foreground Service Declaration (`FOREGROUND_SERVICE_MEDIA_PLAYBACK`)**: Used solely for continuous background news audio playback with Android system `MediaSession` lock-screen/notification transport controls (`HarkMediaService`).
