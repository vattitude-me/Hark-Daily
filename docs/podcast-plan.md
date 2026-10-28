# Podcast Mode: Plan

Status: **proposed, not yet built.** Tasks are in [podcast-tasks.md](podcast-tasks.md).
Any model (Sonnet, then Gemini Flash) can resume from the first unchecked task.

## 1. Goal

Replace ⚡ Rapid Fire with a **Podcast mode**. Full Brief stays exactly as it is.

- Two hosts, **Matthew** and **Kelly**, chat in short back-and-forth turns.
- The chat is built from the day's real news. For example:
  - "Good morning Kelly, how are you doing this morning?"
  - "Big day for AI, and this El Niño story is a little scary."
- The stories are still read by the existing narrator clips.
- The banter is **dynamic**. A listener with 3 categories, or a reduced story count, gets a shorter chat that only mentions what they will hear.
- Several intro variants, so it doesn't sound the same every morning.
- **Feature-flagged** on the server and in the UI. It can be turned off at any time.
- **Never blocks the brief.** If AI or audio generation fails, the listener falls back gracefully.

## 2. What already exists (and what we reuse)

| Piece | Where | How we use it |
|---|---|---|
| Per-story clips, shared by all users, per narrator voice | `story_audio`, `app/storypack.py::voice_scripts` | Unchanged. Podcast mode plays these as the "news segments". |
| Voiced notes (greeting, intros, outro) plus a `pack_ready` marker | `voice_notes`, `build_notes`, `NOTES` | Pattern to copy for podcast clips. |
| Client assembles the timeline from the user's lineup | `web/js/storypack.js::buildBriefing` | Add a `podcast` branch next to the current `rapid` branch. |
| LLM copy writer with a provider chain and a template fallback | `app/writer.py::StoryWriter` | Add Grok as a provider and a dialogue writer on the same chain. |
| Voices `matthew_reference` and `kelly_reference` | `cfg.story_voices` | Host voices. No new voice work. |
| Env-driven config | `app/config.py` | Add the flag and key here. |

**Key constraint:** audio is generated once per day and shared by everyone. The banter therefore can't be written per user. Instead we generate **modular pieces** that the browser combines according to the user's lineup.

## 3. Design

### 3.1 Modular banter pieces (generated once per day)

| Piece | Count | Content |
|---|---|---|
| `pod_open_{n}` | 3–4 variants | Greeting chat, with no news in it. "Good morning Kelly, how are you doing?" Some variants mention the day, the weather or the season. |
| `pod_tease_{section}` | 1 per section | 2–4 turns reacting to that section's **top headline**. "Exciting news on AI today…", "This El Niño story is scary…". |
| `pod_bridge_{section}` | 1 per section | 1–2 turns that lead into that section's stories, in tone with the topic: serious, light or techy. |
| `pod_close_{n}` | 2–3 variants | A short sign-off chat. |

The browser builds the show from the user's lineup:

```
open variant (picked by hash(date + user))
 → teasers for up to 3 chosen sections (only the sections they have)
 → for each chosen section: bridge → that section's story clips
 → close variant
```

- With 1–2 sections, there is one teaser or none.
- With 6 sections, there are 3 teasers, and the rest rely on bridges.
- The "reduced news" count only changes how many story clips play. Banter never names a story that isn't played, because teasers always reference the **#1 story**, which is always included.

### 3.2 Dialogue generation (server, in the daily pack)

1. **Writer chain**: Grok (xAI, OpenAI-compatible) → Gemini → Groq → **template dialogue**. This reuses the `StoryWriter` fallback ideas.
2. **Prompt**: takes the section and its top headline and summary, and the hosts' names. Returns JSON `{turns:[{speaker:"matthew"|"kelly", text}]}`.
   - Rules: conversational, short turns (under 25 words), no facts beyond the supplied text, no URLs, 2–4 turns.
   - A **tone hint per section** (serious, light, techy).
3. **Validation**: strict JSON parse, speaker whitelist, length caps, and a banned-pattern check. Anything invalid counts as a failure of that piece.
4. **Template fallback**: curated line pools per section tone and per open/close variant, filled with the headline. It is not as lively but always ships.
5. **Voicing**: each turn is one TTS call (Matthew's voice or Kelly's voice). Turns are concatenated into **one MP3 per piece**.
6. **Storage**: new table `podcast_clips` (date, key, text, duration, audio_path, `writer`, `voice_pair`) plus a `podcast_ready` marker. Same RLS pattern as `voice_notes`.

### 3.3 Feature toggle (both sides)

- **Server**: `PODCAST_ENABLED` (default `false`) in `app/config.py`.
  - When off, the pack skips podcast generation completely.
  - It also publishes `podcast_enabled` into `app_status`, or an equivalent public flag row.
- **FE**: the mode picker reads that flag.
  - Off: the Podcast button is hidden, a stored `brief-mode=podcast` silently becomes `full`, and Rapid Fire is retained or removed per the open question below.
  - A local override, `?podcast=0`, is useful for testing.
- Flipping the server flag takes effect on the next load. No deploy is needed if it lives in `app_status`.

### 3.4 Error handling and fallback ladder

| Failure | Behaviour |
|---|---|
| Flag off | Podcast mode is not offered. |
| Grok/LLM fails or returns bad JSON | Next provider, then template dialogue. The piece is marked `writer=built-in`. |
| TTS fails for one piece | The piece is skipped. Banter is optional, so the show still plays without it. |
| `podcast_ready` marker missing for the day | FE falls back to the **Full Brief** and shows a small notice: "Podcast isn't ready today, here's the full brief." |
| A needed section teaser or bridge is missing | FE drops just that piece and plays the stories. |
| Entire podcast stage crashes | The pack still publishes with `PodcastIncomplete` logged to `run_log`. **Stories are never held back by banter.** |

The podcast stage runs **after** stories and notes are marked ready, in its own try/except.

## 4. Phases

1. **P0, Foundations**: config flag and key, schema, status flag, test fixtures.
2. **P1, Dialogue writer**: Grok provider, prompt, validation, template fallback, unit tests.
3. **P2, Audio pipeline**: per-turn synthesis, concatenation, upload, `podcast_clips` rows, `podcast_ready`, integrated into `build()`, with failure isolation.
4. **P3, Frontend**: flag-aware mode picker, `buildBriefing` podcast branch, ready-gate fallback, welcome sheet and copy.
5. **P4, Hardening**: end-to-end dry run with the fake writer and TTS, docs update, Android parity decision.

## 5. Testing

- Unit tests (pytest, `tests/`): validation, the template fallback, the chain fallthrough on provider errors, flag-off no-ops.
- A JS test, or a manual script, for `buildBriefing` with 1, 3 and 6 sections plus the missing-piece cases.
- A manual run with `PODCAST_ENABLED=true` against fake TTS, then once against the real voice service.

## 6. Open questions

1. **Rapid Fire**: remove it as the request says ("instead of"), or keep it behind its own flag? Default: **hide it, keep the code**, so it is easy to restore.
2. **Story voices in podcast mode**: keep the user's chosen narrator, or let the hosts read the stories? Default: **keep the narrator** and use Matthew/Kelly for banter only.
3. **Grok**: which model? Default `grok-3-mini` via `https://api.x.ai/v1`. Put the key in `.env` as `GROK_API_KEY`. **Don't paste it in chat.**
4. **Android app**: web first, then port. Confirm.
5. **Turn length**: how long should the banter be in total (default about 60–90 s)?

## 7. Model strategy

- Plan: Claude Opus (medium). Build: Claude Sonnet (medium). Continue with Gemini Flash (high) if quota runs out.
- I can't switch models myself. Switch in the UI.
- Task state lives in [podcast-tasks.md](podcast-tasks.md), so any model can resume.
