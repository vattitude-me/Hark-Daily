# Technical guide

Hark Daily is a daily news podcast. It turns the day's news into a short episode. A scheduled job builds the audio once a day. The apps download the clips and assemble an episode on the device, based on each listener's topics and settings.

## Overview

![Architecture: a daily build produces MP3 clips, which go to cloud storage and a database. The web, Android and iOS apps build a playlist from the public manifest and stream the clips.](diagrams/architecture.svg)

## Components

- A Python pipeline that reads feeds, writes scripts and dialogue, packs the audio and uploads it.
- A text-to-speech service that turns scripts into audio.
- A web app that does the playback. Android and iOS shells load the same hosted app.
- A hosted database and file storage for clips, notes and run status.

## 1. News sources

The pipeline reads RSS feeds. Each edition (Canada, US, India) has 8 sections. AI and science are shared, so they are voiced once and used by all three editions.

| Section | Canada | US | India |
| :--- | :--- | :--- | :--- |
| Top stories | CBC News | New York Times | The Hindu |
| Markets | CBC Business | MarketWatch | Economic Times |
| AI | TechCrunch | TechCrunch | TechCrunch |
| Tech | BetaKit | The Verge | ET Tech |
| Politics | CBC News | NPR | Indian Express |
| Entertainment | CBC News | Variety | Indian Express |
| Science | ScienceDaily (CBC fallback) | same | same |
| Sports | CBC News | CBS Sports | ESPNcricinfo |

US and India section keys have a suffix, for example `top_us` and `markets_in`. Shared sections use plain keys (`ai`, `science`). The pipeline keeps the top 5 stories per section after removing duplicates.

## 2. Scripts and dialogue

- Each article is downloaded and reduced to a title, lead image and body text.
- A summarizer strips datelines and captions, then picks 2 or 3 key sentences. A script runs about 22 seconds.
- A dialogue writer produces the two-host conversation. Matthew gives the facts. Kelly adds the angle or what it means. Each turn is 20 words or fewer. The pieces are:
  - `pod_open_*`, the opening
  - `pod_tease_<section>`, a reaction to the section's top story
  - `pod_bridge_<section>`, the lead-in to a section
  - `pod_close_*`, the sign-off
- Scripts avoid time-of-day phrases like "good morning", so an episode works at any hour.
- The LLM layer tries each provider in order and moves to the next one if a call fails or hits a rate limit.

## 3. Voice synthesis

A local service runs the Chatterbox-Turbo model. The pipeline starts it before a run and stops it after.

- Voices are Matthew (`matthew_reference`) and Kelly (`kelly_reference`).
- A full run (3 editions, about 35 stories and 20 dialogue pieces) takes 15 to 20 minutes.
- Long scripts are split at sentence ends and joined at zero crossings, so there are no clicks.
- A pronunciation lexicon fixes names, acronyms and numbers.
- Clips are encoded as 64 kbps MP3.

The service exposes a small HTTP API: a health check, a list of voices, and a synthesize call that returns MP3 bytes for a given text and voice.

## 4. Fixed voice notes

Greetings, section intros and the sign-off never change, so they are voiced once and kept.

- Each voice has 12 notes: 3 greetings (morning, afternoon, evening), 8 section intros and 1 sign-off.
- Only missing notes are voiced. Most days that means no calls.
- Each day gets pointer rows that reference the fixed files.
- Old-day cleanup skips the fixed notes.

## 5. Storage and database

Audio lives in cloud object storage, grouped by day for stories and dialogue, plus a fixed area for notes and a public manifest for each day's pack.

Main tables:

| Table | Holds |
| :--- | :--- |
| `story_audio` | One row per story clip. Key is `(date, section, rank, voice)` |
| `podcast_clips` | One row per dialogue piece. A `podcast_ready` row marks the day complete |
| `voice_notes` | Greetings, intros and the `pack_ready` marker |
| `profiles` | Signed-in users' settings as JSON |
| `push_subscriptions` | Web push endpoints |
| `app_status`, `run_log` | Run progress and history |

The app only shows a day once its `pack_ready` and `podcast_ready` markers exist, so listeners never get a half-built episode.

## 6. The app

All three platforms run the same web code. The Android and iOS shells load the hosted site, so a web deploy updates every platform.

### Building the episode

The playlist builder turns the pack into a list of clips:

1. Picks the greeting from the listener's local time.
2. Orders sections by the listener's `section_order`. The default is top, markets, AI, tech, politics, entertainment, science, sports.
3. Takes the wanted number of stories per section. The default is 5 for top stories and 3 for the rest.
4. In podcast mode, adds the dialogue pieces around each section. In Full Brief mode, adds the fixed section intros instead.
5. Puts a 0.8 second pause between clips.

### Playback

The player plays one clip at a time and preloads the next. It updates the lock screen through the Media Session API. On Android, a native foreground service keeps audio playing with the screen off.

### Weak networks

A network module decides whether the connection is fine, slow or offline. The listener only sees real evidence: the browser is offline, playback waited several seconds for data, or two requests timed out within two minutes. `navigator.connection` is only a hint. It stretches timeouts and delays preloading, and never shows a banner, because Chrome's estimate dips on fast Wi-Fi.

- On a slow link, request timeouts are three times longer and the app waits to preload the next clip.
- A short banner says "Slow connection" or "You're offline". In the player it sits in the top bar between the menu and story list buttons.
- A clip that fails to load retries up to 3 times and resumes where it stopped.
- The splash screen tells the user if loading takes more than 4 seconds and offers a retry after 12.

### Offline shell

A service worker caches the app shell. Code files are network-first, so a deploy reaches users on the next load, with a short fallback to the cache. Bump the cache version, and the `?v=` numbers in `index.html`, when you change a cached file.

### Shared stories

Story links open the app at that story. If the date has aged out, the app shows a dialog that offers today's episode. A serverless function gives link previews to chat apps and social sites.

### Feedback

The feedback form posts to a serverless function that forwards it to a Discord webhook. It blocks spam with a hidden honeypot field, a simple math question and a 60 second cooldown, and it removes `@everyone` and `@here` mentions.

### Analytics

Google Analytics loads only after the user accepts the consent banner. Events tracked: `share`, `shared_link_open`, `select_content` and `footer_link_click`.

## 7. Daily run

A scheduled job on a dedicated machine runs the build each morning, before listeners wake up. See [nightly.md](nightly.md) for the schedule and recovery steps. A separate background worker handles requests the app queues, such as admin rebuilds and account deletions.

## 8. Pre-prod

Pre-prod is a separate backend project for testing changes. Pack runs and checks against it refuse to touch production. Preview builds and local development use Pre-prod automatically.

## 9. Configuration

Copy `.env.example` to `.env` and fill in the values. The main settings:

| Variable | Purpose |
| :--- | :--- |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | Backend project and service key for uploads |
| `VOICE_SERVICE_URL`, `VOICE_DIR` | Voice service address and reference voice clips |
| `STORY_VOICES`, `PODCAST_HOSTS` | Voices for story clips and the two hosts |
| `PODCAST_ENABLED` | Build the two-host dialogue |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | LLM fallbacks |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Web push |

## 10. Commands

```bash
python -m app pack --edition ca,us,in     # build today's pack
python -m app pack --check                # show what today's pack has
python -m app pack --podcast-only --force # redo the dialogue only
python -m app pack --showcase-only        # republish the public manifest
```

## 11. Tests

```bash
npm test                                  # web app
.venv/bin/python -m pytest -q tests       # pipeline
cd android && ./gradlew testDebugUnitTest # Android shell
```

GitHub Actions runs the web and Python tests on every pull request.
