# Podcast Mode: Tasks

Plan: [podcast-plan.md](podcast-plan.md). Tick a box when the task is done and tests pass.

**Resume rule:** start at the first unchecked task. Don't skip phases. Run `pytest` after every backend task.
Hand-off log: add one line per session at the bottom.

## P0, Foundations
- [x] P0.1 `app/config.py`: add `podcast_enabled` (`PODCAST_ENABLED`, default false), `podcast_hosts` (any two voice ids, default matthew_reference, kelly_reference). LLM is the existing Groq → Gemini chain; no Grok
- [x] P0.2 (flag lives in `app_status.data.podcast`, set by worker `_base_status`) `supabase/schema.sql`: `podcast_clips` table, RLS read-only for anon, indexes. Plus a public flag source (`app_status` row or equivalent)
- [x] P0.3 `.env.example` / docs: document the new vars. No secrets committed

## P1, Dialogue writer
- [x] P1.1 `app/podcast.py`: piece catalogue (`pod_open_N`, `pod_tease_<sec>`, `pod_bridge_<sec>`, `pod_close_N`) and section tone map
- [x] P1.2 Template dialogue pools (the guaranteed fallback)
- [x] P1.3 Dialogue call reuses the existing Gemini/Groq chain, then template (Groq key verified working 2026-10-27)
- [x] P1.4 Prompt plus strict JSON validation (speakers, turn count, word caps, no URLs)
- [x] P1.5 Tests `tests/test_podcast.py`: validation, fallthrough, template output, flag off

## P2, Audio pipeline
- [x] P2.1 Per-turn TTS with host voices, concatenate to one MP3 per piece
- [x] P2.2 Upload plus `podcast_clips` rows, `podcast_ready` marker
- [x] P2.3 Hook into `storypack.build()` after stories/notes are ready, in an isolated try/except (`PodcastIncomplete` logged, never blocks)
- [x] P2.4 Skip pieces already built (idempotent, honours `force`)
- [x] P2.5 Tests with a fake TTS: partial failure, full failure, flag off

## P3, Frontend
- [x] P3.1 `web/js/api.js` / `app.js`: fetch the podcast flag and clips
- [x] P3.2 Mode picker: Podcast replaces Rapid Fire (`index.html`, `styles.css`, `sheets.js`); hidden when flag off; stored `podcast` mode falls back to `full`
- [x] P3.3 `buildBriefing`: podcast branch (open → teasers → bridge+stories → close), respects the user's lineup and counts
- [x] P3.4 Ready-gate fallback to Full Brief with a notice. Missing pieces are skipped
- [x] P3.5 Copy updates (landing and welcome text mentioning Rapid Fire)

## P4, Hardening
- [x] P4.1 End-to-end dry run (fake writer + fake TTS) with 1, 3 and 6 sections
- [ ] P4.2 (needs you: apply `podcast_clips` SQL in Supabase, set `PODCAST_ENABLED=true`, run `python -m app pack`) Real run against the voice service and Grok; check the audio by ear
- [x] P4.3 Update `docs/TECHNICAL.md` and README
- [ ] P4.4 Android parity (next): `StoryPack.kt` podcast branch, `Repo`/`Supabase` podcast_clips fetch, mode picker in Today/Settings, hide Rapid, bump versionName/versionCode, add Kotlin test mirroring `tests/js/podcast.test.mjs`

## Hand-off log
- 2026-10-27: P3 web done (`web/js/storypack.js` planPodcast/buildBriefing, `app.js` flags + fallback, `sheets.js`, `index.html`, `config.js` FEATURES). `node --test tests/js` 8 pass; pytest 137 pass. Released as 0.1.62 (flag off by default). Remaining: P4.2 real run, P4.4 Android.
- 2026-10-27: P1+P2 done in `app/podcast.py` (+`tests/test_podcast.py`, 137 tests pass; live Groq banter verified). Hooked into `storypack.build()` (isolated). Next: P3 frontend. FE note: keep total banter ≤90 s by adding pieces in priority order (open, teasers for top 3 sections, close, then bridges) until the budget is used; clip rows carry `duration`.
- 2026-10-27: Decisions: hide Rapid Fire (keep code); host pair is config (`PODCAST_HOSTS`); banter 60–90 s; web first then Android APK; Groq (not Grok). P0 done (pending tests).
- 2026-10-27: Plan and tasks written. No code yet. Waiting on answers to the open questions in the plan.
