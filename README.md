# ☀️ Morning Brief

Your daily news on cards, **read aloud every morning by a natural neural voice**. It covers
**top Canadian news** and **AI & tech**, plus any sites or articles you add yourself.

![Morning Brief on desktop](docs/screenshots/desktop.png)

| Mobile (dark) | Swipe deck | Voice picker |
|---|---|---|
| ![](docs/screenshots/mobile-dark.png) | ![](docs/screenshots/mobile-swipe.png) | ![](docs/screenshots/settings.png) |

> Screenshots use the fictional sample feeds in `tests/fakenews.py`.

## What it does

Every morning (06:30 Toronto time by default) the app:

1. **Gathers** headlines from RSS feeds (CBC, Global News, The Globe and Mail, National Post, CityNews
   Toronto, TechCrunch, The Verge, MIT Technology Review, Ars Technica, VentureBeat, The Decoder,
   BetaKit, Hacker News…) and from **your own links**.
2. **Ranks** them. When several outlets cover the same story it becomes one card, and wide coverage
   pushes it up. AI stories get a boost in AI & Tech, and deals or gift guides are filtered out.
3. **Reads** the full articles with [trafilatura](https://github.com/adbar/trafilatura).
4. **Writes** a 40–60 word card summary and a spoken script for each story. It uses Claude if you
   add an API key; otherwise a built-in extractive summarizer does it.
5. **Records** one MP3 with a neural voice and chapter markers for every story.

### Highlights

- 🎧 **Natural voice, not robotic.** The default is [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), an
  open-source (Apache-2.0) neural TTS model that runs on your own CPU. You can also pick Microsoft's
  neural voices through [edge-tts](https://github.com/rany2/edge-tts), which include **Canadian English** (Clara, Liam).
  Tap ▶ in Settings to hear a sample of each voice.
- 🃏 **Card UI** with a grid or InShorts-style **swipe deck**. Tap **Listen** on any card to jump the
  audio to that story. The card that's playing glows as the briefing moves along.
- ➕ **Add any news link.** Paste a site, section page, RSS feed or single article. The app finds the
  feed automatically, falls back to scraping headlines, and shows a preview before you add it. A single
  article goes into your next briefing once.
- 🌤️ Weather for Toronto (or any city) in the intro, via Open-Meteo (no key needed).
- 📱 Installable **PWA** with lock-screen controls (Media Session): play/pause, ±15/30 s, next/previous story.
- 🌙 Light and dark themes, playback speed, resume where you left off, saved stories, and 14 days of past briefings.
- 🔒 Optional password (`APP_PASSWORD`) if you expose it to the internet.

## Quick start (Docker)

```bash
cp .env.example .env        # optional: add ANTHROPIC_API_KEY, APP_PASSWORD
docker compose up -d --build
open http://localhost:8000
```

Press **Build my briefing** for your first one. After that it builds automatically every morning.
The voice model (~350 MB) is baked into the image, so there's nothing extra to download.

## Deploy on Render

1. In the Render dashboard choose **New → Blueprint** and pick this repository. Render reads
   [`render.yaml`](render.yaml).
2. When asked, set **`APP_PASSWORD`** (you'll use it to sign in; any username works). You can also set
   **`ANTHROPIC_API_KEY`**, or leave it blank.
3. Click **Apply**. The first build takes about 5 minutes. Then open the `onrender.com` URL and press **Build my briefing**.

The Blueprint uses the **Starter** plan with a 1 GB disk for your data. It uses the Microsoft neural
voices (Canadian *Clara* by default) because the Kokoro model needs about 1.2 GB of RAM. To use
Kokoro, change the plan to **Standard** and set `TTS_ENGINES=kokoro,edge`.

## Run without Docker

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app setup      # download the Kokoro voice model (~350 MB, once)
python -m app serve      # http://localhost:8000
```

Other commands:

```bash
python -m app build      # build today's briefing right now (handy for cron)
python -m pytest         # run the tests (offline; no network needed)
```

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Lets Claude write the summaries and a radio-style script. Without it the built-in summarizer is used. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model used for writing. |
| `BRIEFING_TIMEZONE` | `America/Toronto` | Time zone for the daily schedule. |
| `APP_PASSWORD` | – | Turns on HTTP Basic auth (any username). |
| `DATA_DIR` | `./data` | SQLite database, briefings and MP3s. |
| `MODEL_DIR` | `$DATA_DIR/models` | Kokoro model files. |
| `KEEP_DAYS` | `14` | How many days of briefings to keep. |
| `SCHEDULER_ENABLED` | `1` | Set to `0` to disable the built-in daily scheduler. |
| `ALLOW_PRIVATE_URLS` | `0` | Allow sources on private/LAN addresses. |
| `TTS_ENGINES` | `kokoro,edge` | Voice engines to offer. Use `edge` on hosts with under ~1.5 GB RAM. |
| `DEFAULT_VOICE` | Kokoro *Heart* | Voice used until you pick one in Settings, e.g. `edge:en-CA-ClaraNeural`. |

Voice, speaking pace, briefing time, stories per section and weather city are set in the app under
**Voice & settings**. Sources are managed under **Sources**. Built-in sources can be switched off,
and your own sources can be removed.

## Hosting ideas

- **At home:** a Raspberry Pi 4/5 or any always-on computer running `docker compose up -d`. Kokoro
  runs fine on CPU; a 5-minute briefing takes about 1–3 minutes to record.
- **Cloud:** Render (see above) or any container host with a persistent volume for `/data`
  (Fly.io, Railway, a small VPS). Set `APP_PASSWORD` when it's public.

## Project layout

```
app/
  main.py         FastAPI app: JSON API, audio files, web UI
  briefing.py     daily pipeline: fetch → rank → read → write → record
  fetcher.py      RSS/Atom (feedparser), feed discovery, page scraping, article extraction (trafilatura)
  ranking.py      duplicate clustering and scoring
  summarizer.py   extractive summarizer (no API key needed)
  writer.py       card copy and spoken script (Claude or template)
  tts/            Kokoro and Edge neural voices, text clean-up for speech
  audio.py        segment levelling, chapter timing, MP3 encoding
  jobs.py         background builds and the daily schedule
  db.py           SQLite sources and settings
web/              vanilla JS PWA (no build step)
tests/            offline tests with sample feeds
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/briefing/latest`, `/api/briefing/{YYYY-MM-DD}`, `/api/briefings` | Briefings and archive |
| POST | `/api/briefing/generate` | Build now (runs in the background) |
| GET | `/api/status` | Build progress and next scheduled run |
| GET/POST/PATCH/DELETE | `/api/sources[/{id}]` | Manage sources |
| POST | `/api/sources/detect` | Preview what a link is before adding it |
| GET | `/api/voices`, `/api/voices/preview?voice=…` | Voices and samples |
| GET/PUT | `/api/settings` | Preferences |

Audio lives at `/media/{date}/briefing.mp3`.
