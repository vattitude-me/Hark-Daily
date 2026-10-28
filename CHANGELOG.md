# Changelog

All notable changes to the **Morning Brief** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.68] - 2026-10-28

### Fixed
- **Web PWA Public Storage Fallback & Multi-Host Ready Check**:
  - Implemented CDN public storage fallback in `web/js/api.js` (`publicPack`) matching Android's `Supabase.kt`. Web now automatically falls back to fetching `showcase/pack-$date.json` or `showcase/pack.json` from Supabase Storage CDN if PostgREST queries fail or tables lack anon read permissions.
  - Fixed multi-host ready check in `web/js/app.js` (`loadStoryPack`): handles concatenated host voice IDs in Podcast mode (e.g. `matthew_reference+kelly_reference`) by splitting hosts and validating each narrator against `pack_ready` notes.
  - Added older news fallback in `web/js/app.js`: if today's pack is unavailable or mid-recording, the web app automatically falls back to `latestStoryDate` instead of rendering "Not published yet".
  - Fixed story count reload in Android (`AppViewModel.kt`): added `force = true` reload when story counts or briefing editions change, preventing ExoPlayer from continuing to play previous queued media items.
- Bumped PWA service worker cache to `hark-daily-v20` and Android version to `0.1.68` (`168`).

---

## [0.1.67] - 2026-10-28

### Fixed
- **Atomic Media Loading & Playlist Synchronization on Story Count Changes**:
  - Replaced separate asynchronous `load()` and `seekGlobal()` calls in Android with atomic `c.setMediaItems(items, startIndex, startPositionMs)`. This eliminates race conditions where ExoPlayer evaluated seek indices against the old timeline before Binder IPC delivered the new timeline, which previously caused the voice to read an unrelated story from the old lineup while displaying a different card on screen.
  - Synchronized `nowPlaying` and `briefing` state flows across `doFetchPack()`, `load()`, and `setBriefingMode()`, ensuring the floating MiniPlayer and the broadsheet card view always reference the exact same story lineup and timeline timestamps.
  - Enhanced Web PWA `saveAll()` to retain active story ID and seek cleanly to the target story upon lineup updates.

### Infrastructure
- **Full GCP Infrastructure Decommission & Mac Local Automation**:
  - Permanently turned off and deleted all Google Cloud Platform components (Compute Engine VM `morning-brief-voice`, attached 60GB disk, firewall rules, Cloud Run jobs `morning-brief-pack` and `morning-brief-report`, Cloud Scheduler jobs, and Artifact Registry repository `voice-service`). Zero GCP cost or cloud stockouts.
  - Configured local Mac M3 Pro as primary daily briefing runner with `scripts/morning_pack_mac.sh` and LaunchAgent `me.vattitude.harkdaily.morning` scheduled at 06:00 AM daily, running Apple Silicon MPS Chatterbox-Turbo with `caffeinate -i -s -m`.
- Bumped PWA service worker cache to `hark-daily-v19` and Android version to `0.1.67` (`167`).

---

## [0.1.66] - 2026-10-28

### Fixed
- **Audio Queue & Lineup Desynchronization on Story Count Changes**:
  - `Briefing.mediaId` now incorporates a cryptographic fingerprint of the card lineup and voice (`$version-$hash`), ensuring ExoPlayer detects when story counts, section order, or narrators change.
  - Previously, `Briefing.mediaId` was static (`$date-$mode@$version`), causing ExoPlayer to ignore lineup changes and continue playing stale audio clips (e.g. reading removed Politics stories while highlighting unrelated Tech stories on screen).
  - Added double verification in `load()` checking both `mediaId` and `mediaItemCount` mismatch.
  - Seamless resume: if the currently playing story remains in the modified lineup, playback seamlessly resumes at the exact second; if the story was removed by the user, playback cleanly resets and stops.
  - Web PWA: updated `saveAll()` to immediately rebuild and reload `state.briefing` upon saving topic/source changes.
- Bumped PWA service worker cache to `hark-daily-v18` and Android version to `0.1.66` (`166`).

---

## [0.1.65] - 2026-10-27

### Added
- **Default Podcast Edition**: Made Podcast Edition the default playback mode across both Web (`app.js`, `sheets.js`) and Android (`Prefs.kt`, `AppViewModel.kt`), automatically falling back to the Full Brief when podcast banter is unavailable.
- **Alternating Host Voices in Podcast Mode**: News stories are now co-anchored and alternated between both hosts (Matthew & Kelly) across the entire briefing instead of a single voice reading all stories. The narrator credit displays both co-hosts ("Matthew & Kelly").
- **Em-dash and En-dash Normalization**: Stripped em-dashes (`—`) and en-dashes (`–`) across podcast dialogue generation, story pack synthesis, and the `voice_service` pipeline, converting them to natural comma pauses to prevent Chatterbox from speeding through hyphens.
- Bumped PWA service worker cache to `hark-daily-v17` and Android version to `0.1.65` (`165`).

---

## [0.1.64] - 2026-10-27

### Added
- **Podcast Mode for Android**: Full client parity with web for two-host conversational podcast mode (`PODCAST_HOSTS`, default Matthew & Kelly).
  - Fetches and stitches daily podcast banter (`podcast_clips`) dynamically matching listener topic preferences within the 90-second banter budget.
  - Added "Podcast Edition" pill selector on `TodayScreen` and dedicated row in `SettingsScreen` with violet badge and microphone iconography.
  - Seamless fallback handling: if banter is not yet published for the day or fails, automatically falls back to the Standard Edition and displays an unobtrusive status note.
  - Unit test coverage in `StoryPackTest.kt` verifying timeline assembly, teaser/bridge budget enforcement, and fallback behavior.
- Bumped PWA service worker cache to `hark-daily-v16`.

---

## [0.1.63] - 2026-10-27

### Added
- **Chatterbox voice tags in podcast banter**: hosts can now `[laugh]`, `[chuckle]`, `[sigh]`, `[gasp]` and so on, performed natively by the voice. Tags are whitelisted, capped at 2 per piece, stripped from the Top stories and Politics banter, and removed from captions. Any other bracketed text rejects the piece.

- `python -m app pack --podcast-only [--force]`: writes and voices the banter for the stories already published today, without fetching news or re-voicing stories. Supabase SQL for the new table is also in `supabase/podcast_clips.sql`.

---

## [0.1.62] - 2026-10-27

### Added
- **Podcast mode (web, feature-flagged)**: two configurable hosts (`PODCAST_HOSTS`, default Matthew and Kelly) chat around the day's news. Banter is written once a day by the existing Gemini/Groq chain with validated output and a built-in template fallback ([`app/podcast.py`](app/podcast.py)), voiced per host, and assembled client-side to match each listener's categories within a 90 s banter budget.
- Kill switches on both sides: `PODCAST_ENABLED` (server, off by default, published via `app_status`) and `FEATURES.podcast` (`web/config.js`). Any failure leaves the Full Brief untouched.
- `podcast_clips` table in `supabase/schema.sql` (run it before enabling the flag).

### Changed
- Rapid Fire is hidden (`FEATURES.rapid = false`), not removed. Android parity is next.
- Bumped PWA cache to `hark-daily-v15`.

---

## [0.1.61] - 2026-10-27

### Added
- **Modular Voice Lineup (C-3PO Flagship, Matthew & Kelly)**:
  - Rotated the active narrator lineup to permanent flagship anchor C-3PO (`c3po_reference`) alongside modular neural narrators Matthew (`matthew_reference`) and Kelly (`kelly_reference`).
  - Added dynamic voice architecture across Android (`Voices.kt`, `SettingsScreen.kt`) and Web (`api.js`): any present or future voice ID is dynamically formatted with clean title-casing and default avatars without client regressions.
  - Added vibrant visual gradients for Matthew (royal blue) and Kelly (rose) in Android Settings.
- **Section Starvation Protection & ScienceDaily Feed**:
  - Implemented 3-tier recency backfill in `app/topics.py` (`top_n()`) with pool expansion to 20 stories to guarantee full 5-story sections during multi-run editions.
  - Added ScienceDaily source with automated fallback to CBC Science.
  - Added same-day unexpired story backfill and rank-shifted audio reuse (`existing_by_url`) in `app/storypack.py`.
- **Cache & API Updates**:
  - Bumped PWA service worker offline cache to `hark-daily-v14`.
  - Updated API documentation and client integration guides in `API_DOCUMENTATION.md` and `docs/TECHNICAL.md`.

---

## [0.1.60] - 2026-10-25

### Fixed
- **Dynamic Version Display in Settings**:
  - Replaced hardcoded version string (`v0.1.47`) in `SettingsScreen.kt` with dynamic `BuildConfig.VERSION_NAME`, ensuring the settings footer always reflects the true build version.
  - Added memory rule in `.agents/rules/commit-and-version.md` to guarantee UI components always bind dynamically to `BuildConfig.VERSION_NAME`.

---

## [0.1.59] - 2026-10-25

### Fixed
- **Clean Card Summary Display (No Duplicate Headline or Banter on Screen)**:
  - Fixed story cards in Android and Web displaying the repeated headline and conversational filler in the card body text. The headline and filler remain exclusively in the voiced audio narration, while visual cards now display the clean, readable article summary.
  - Added `stripHeadlineAndFiller` across Android (`StoryPack.kt`, `Briefing.kt`) and Web (`storypack.js`), ensuring even existing briefings instantly render clean body text without app-level duplication.
- **Stripped Editorial Lead-in Prefixes (BetaKit "The news:")**:
  - Filtered out publication section labels (`"The news:"`, `"From the source:"`, `"Why it matters:"`, `"The big picture:"`, etc.) in `app/summarizer.py` so they are never voiced or shown in card summaries.
  - Bumped PWA service worker cache to `hark-daily-v13`.

---

## [0.1.58] - 2026-10-25

### Added
- **Broadcast Headline Narration & Podcast Banter Fillers**:
  - Upgraded story scripts to naturally read `[Headline] + [Podcast Banter Filler] + [Body Summary]`, delivering a polished podcast/radio listening experience for eyes-free listeners.
  - Added rotating friendly conversational connectors across stories (`"Here are the details:"`, `"Here's what you need to know:"`, `"Taking a closer look:"`, `"Here's what's happening:"`, `"According to the reporting:"`, `"In the details:"`, `"Behind the headline:"`).
- **60% Word-Overlap Deduplication Filter**:
  - Implemented automatic token overlap analysis in `app/summarizer.py`: when article lead sentences repeat the headline verbatim ($\ge 60\%$ word overlap), sentence 1 is dropped, advancing the narrator directly to rich background details.
- **Option A Editorial Hero Card Layout (Android & Web)**:
  - **Hero Lead Card**: Currently playing / active stories expand to feature a prominent full-width 16:9 editorial hero banner image (`height: 180dp`, `RoundedCornerShape(16.dp)`) with subtle border and crisp typography.
  - **Enlarged Secondary Thumbnails**: Secondary story cards now feature generous, prominent 72×72dp thumbnails with rounded corners (12dp).
  - **Mini Player / Hero Art**: Enlarged playback artwork box from 48dp to 56dp with 14dp rounded corners.
  - **Mobile Web Imagery Restored**: Removed `.story-thumb { display: none; }` on phone viewports (`@media (max-width: 600px)`), enabling rich photography across mobile web.

---

## [0.1.57] - 2026-10-24

### Added
- **Permanent Static Voice Notes Library & VM Pre-Closure Guard**:
  - Voice transitions and greetings (11 notes per voice: 3 greetings, 7 section intros, 1 outro) are now permanently stored under `notes/static/{note_key}-{voice}.mp3` and indexed under sentinel date `2000-01-01`.
  - Added `ensure_static_notes()` pre-closure verification: when daily generation runs or a new voice is added, any missing static notes are automatically synthesized using the active GPU VM session before VM shutdown.
  - Subsequent runs reuse existing static notes instantly with 0 GPU synthesis time and zero storage audio duplication.
  - Hardened `prune_older()` to protect `STATIC_DATE` rows and guarantee audio files under `notes/static/` are permanent and never deleted.
  - Backfilled and verified all 44 static notes across C-3PO, Alice, Mike, and Jerry in Supabase storage and database.
- **Documentation & Legal Updates**:
  - Completely updated `README.md` to showcase the new multi-provider architecture (CBC News, TechCrunch, BetaKit), flagship voice lineup (C-3PO & Alice), Android pull-down-to-refresh, and dual listening modes (Full & Rapid).
  - Refreshed high-resolution desktop and mobile UI screenshots in `docs/screenshots/`.
  - Updated `web/privacy.html` and `web/terms.html` to reflect modern multi-provider news sourcing, shared cloud audio privacy guarantees, and publisher attribution.

---

## [0.1.56] - 2026-10-24

### Added
- **Android Pull-Down-to-Refresh Gesture**:
  - Implemented pull-down-to-refresh on `TodayScreen` using Compose Material3's `PullToRefreshBox` with customized brand indicator styling (`t.cardBg`, `t.ink`).
  - Added `isRefreshing` state flow and updated `refreshPack()` in `AppViewModel` to trigger background story and audio re-fetch while retaining current briefing state.
  - Bumped Android app version to `0.1.56` (`156`).

---

## [0.1.55] - 2026-10-24

### Changed
- **Configured Canadian Tech via BetaKit**:
  - Set `tech` section source to BetaKit (`https://betakit.com/feed/`) in `app/topics.py`.
  - Bumped PWA service worker cache to `hark-daily-v11` and Android version to `0.1.55` (`155`).

---

## [0.1.54] - 2026-10-24

### Changed
- **Provider-Agnostic Topics Architecture (`app/topics.py`)**:
  - Removed vendor-specific file naming: renamed `app/cbc.py` to generic `app/topics.py` and completely deleted deprecated `app/guardian.py`.
  - Configured multi-provider briefing topics:
    - CBC News: Top Stories, Politics, Entertainment, Science, Sports.
    - TechCrunch: AI category (`techcrunch.com/category/artificial-intelligence/feed/`) and Tech (`techcrunch.com/feed/`).
  - Updated all imports, test harnesses (`tests/test_topics.py`), Android/Web references, and documentation.
  - Bumped PWA service worker cache to `hark-daily-v10` and Android version to `0.1.54` (`154`).

---

## [0.1.53] - 2026-10-24

### Changed
- **Web & Android UI Voice Synchronization (C-3PO Default, Alice Alternate)**:
  - Updated Web PWA voice selectors in `web/js/api.js` (`BUILTIN_VOICES`) to offer active voices: C-3PO (`c3po_reference`) as flagship default and Alice (`her_reference`) as alternate. Bumped PWA service worker cache to `hark-daily-v9`.
  - Updated Android app (`PACK_VOICES` in `Voices.kt`) to align with C-3PO first and Alice second. `SettingsScreen` and `packVoice()` automatically default to C-3PO and gracefully discard obsolete narrator selections.
  - Updated Android unit test suite (`SettingsTest.kt`) to assert active 2-voice configuration and fallback behaviors.
- **Robust Error Handling for Removed / Absent GCP Components**:
  - Enhanced `app/gce.py` with immediate fail-fast error detection for removed or decommissioned GCP VM resources (`HTTP 404` or `403`), eliminating previous 180s timeout polling loops.
  - Hardened `stop_vm_verified()` to confirm VM shutdown immediately when the instance does not exist (404), avoiding spurious retry loops or false billing alerts for deleted VMs.
  - Converted unhandled `RuntimeError` on missing `VOICE_SERVICE_URL` to structured `VoiceServiceDown` with actionable configuration guidance.
  - Added `scripts/teardown-gce.sh` for one-command teardown of GCE GPU VMs and persistent disks to completely eliminate recurring GCP costs when desired.
  - Added unit test suite in `tests/test_safety_guards.py` covering GCE 404/403 fail-fast handling, immediate deletion verification, and missing voice URL guards.

---

## [0.1.52] - 2026-10-24

### Changed
- **GCP Cost Optimization & Streamlined Voice Pair (C-3PO Main, Alice Alternate)**:
  - Focused active voice synthesis on C-3PO (`c3po_reference`) as default/main and Alice (`her_reference`) as alternate, halving daily L4 GPU synthesis time from ~26m to ~13m.
  - Updated Cloud Run jobs (`morning-brief-pack`, `morning-brief-report`) live in GCP with `STORY_VOICES=c3po_reference,her_reference` and `STORY_VOICE=c3po_reference`.
  - Pruned 6 dangling untagged container builds from Artifact Registry to reclaim storage space.
  - Adjusted GCE deployment script boot disk size from 60 GB to 40 GB.

---

## [0.1.51] - 2026-10-24

### Changed
- **Renamed Story Pack Module to Reflect CBC & Multi-Provider Architecture**:
  - Renamed `app/guardian.py` to `app/cbc.py` and `tests/test_guardian_sections.py` to `tests/test_cbc_sections.py`.
  - Maintained backward compatibility stub in `app/guardian.py` forwarding all symbols to `app.cbc`.
  - Updated all internal imports, pipeline references, and documentation across Android, Web (`sw.js` cache bumped to `hark-daily-v8`), and tests.

---

## [0.1.50] - 2026-10-24

### Changed
- **Multi-Provider Story Pack & Media Player Filtering**:
  - Transitioned story pack sections to specialized sources: CBC News for Top stories, Politics, Entertainment, Science, and Sports; TechCrunch for AI; and BetaKit for Canadian Tech.
  - Hardened feed parsing in `app/guardian.py` to automatically skip video/audio player stubs (`/player/play/`) in favor of full reporting articles.
  - Added unit test coverage for section provider mappings and media player stub exclusion.

---

## [0.1.49] - 2026-10-22

### Changed
- **Instant Briefing Loading, Screen-Awake Playback & Resilient Cloud Sync**:
  - **Screen Awake During Active Playback & Builds**:
    - Added `FLAG_KEEP_SCREEN_ON` in `MainActivity` whenever the main audio player, onboarding demo, voice preview, or briefing build worker is active, preventing device sleep interruptions.
  - **Single-Fetch Full & Rapid Editions (`StoryPack.fetchBoth`)**:
    - Refactored `StoryPack` to fetch the day's shared `story_audio` and `voice_notes` rows once and assemble both Full and Rapid Fire editions in a single round-trip, with automatic fallback to the latest available briefing date if today's pack is still generating.
    - Persisted `briefingMode` (`full` vs `rapid`) in `Prefs` across app restarts and fixed `TodayScreen` empty-state flicker during initial load.
  - **Public / Guest Access & Resilient Supabase Fallbacks**:
    - Granted `anon` read access to `story_audio` and `voice_notes` in `supabase/schema.sql` and published full guest pack manifests (`showcase/pack.json`) in `app/storypack.py`.
    - Hardened `Supabase.storyAudio()` and `Supabase.voiceNotes()` to seamlessly fall back to public anon queries and showcase storage manifests when an auth token expires or a user is browsing as a guest.
    - Added unit tests in `StoryPackTest.kt` verifying Full and Rapid pack assembly, section ordering, and showcase fallback parsing.

---

## [0.1.48] - 2026-10-22

### Changed
- **C-3PO Flagship Voice, Streamlined Onboarding & Instant Guest Playback**:
  - **C-3PO Front & Center**:
    - Featured C-3PO as the flagship narrator on the Onboarding Welcome screen (*"Today's brief, narrated by C-3PO"* and *"Voiced by C-3PO & more — Your daily news delivered with protocol precision"*).
    - Bundled authentic, high-fidelity C-3PO audio sample directly into the app (`sample_brief.mp3`), letting new users hear C-3PO narrate today's news before signing up.
    - Updated default app narrator voice to `c3po_reference` (C-3PO).
  - **Frictionless 2-Step Onboarding**:
    - Removed mandatory/suggested Google Sign-in step from the onboarding flow entirely. Onboarding now cleanly flows: Welcome (sample C-3PO brief) → Topics selection → Today's live news.
    - Google Account sign-in remains easily accessible within the Settings tab for cloud synchronization and cross-device preferences.
    - Removed premature Edition selector (Full Brief vs. Rapid Fire) from the welcome screen, eliminating cognitive friction for first-time listeners.
  - **Guest Listener Cold-Start & Instant News Loading**:
    - Resolved the *"Today's brief isn't ready yet"* issue encountered by guest users who skipped sign-in. Root cause: Supabase `story_audio` table RLS requires authenticated sessions, returning HTTP 401 for unauthenticated clients.
    - Added `StoryPack.fetchShowcase(voice)` to fetch publicly hosted daily briefing packs (`showcase/sample-${voice}.json`) from Supabase Storage without requiring authentication.
    - `AppViewModel.fetchPack()` now automatically falls back to showcase briefings whenever unauthenticated or when live packs are unavailable, ensuring new and guest users immediately receive and hear today's live news without delays.

---

## [0.1.47] - 2026-10-22

### Changed
- **Audio Follow-Along, MiniPlayer & Editorial Polish**:
  - **Auto-Expand & Smooth Story Follow-Along**:
    - Active playing story now automatically expands to display complete summary, external article link, source citations, and report action, collapsing previously read stories.
    - Added smooth animated follow-along scroll that brings the current story into focus without interrupting recent user scroll gestures.
  - **MiniPlayer Bottom Toolbar Integration**:
    - Fixed date string parsing in briefing media IDs (`substringBefore('@').removeSuffix("-full").removeSuffix("-rapid")`) ensuring `nowPlaying` and player state remain in sync across all playback modes.
    - Floating MiniPlayer now reliably appears above the bottom tab bar whenever the hero player is scrolled out of view on the Today tab or when browsing Sources and Settings tabs.
    - Integrated play/pause transport button and next story button (`|>`) directly into the MiniPlayer with smooth return-to-hero interaction on card tap.
  - **Sources Screen Broadsheet Redesign**:
    - Added **Daily Edition Profile** glass card highlighting total selected stories and calculated audio duration (`~X min audio`).
    - Added category avatar tiles (38dp rounded) with topic-specific iconography (Globe, SmartToy, Computer, AccountBalance, Theaters, Science, SportsSoccer, LocationCity) and category color tints.
    - Replaced disconnected chevron arrows with a unified solid pill capsule for reordering topics and adjusting story counts.
  - **Settings Screen Broadsheet Overhaul**:
    - Added dedicated **Edition Selector** card (Standard Edition vs ⚡ Rapid Fire Edition with 1.1x speed indicator).
    - Redesigned **Narrator Voice Selector** with custom gradient avatar badges (Alice in warm amber, Mike in royal blue, Jerry in emerald green, C-3PO in golden droid brass), active selection glow, checkmarks, and animated audio equalizer previews.
    - Added broadsheet Hark Daily footer with version indicator and legal links.
  - **Onboarding Audio Robustness**:
    - Integrated `DisposableEffect` and navigation hooks to immediately halt demo audio playback when advancing steps, navigating back, skipping, or completing onboarding.
    - Dynamic demo playback speed respects Rapid Fire mode (1.1x speed).
    - Bundled crisp, low-latency sample brief audio asset.

---

## [0.1.46] - 2026-10-22

### Changed
- **Android App Store Readiness & Design Overhaul**:
  - **App Identity & High-Res Icons**:
    - Renamed application to **Hark Daily** across all Android system resources.
    - Generated complete adaptive and mipmap icon suites across all densities (`mdpi`, `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi`) matching the web PWA's obsidian and dawn horizon artwork (`ic_launcher.png`, `ic_launcher_round.png`).
  - **Onboarding Experience Overhaul**:
    - Branded with 80dp glowing Hark Daily app mark and updated tagline: *"The news you hear, not just read."*
    - Added **Preferred Edition Selector** directly into onboarding (Full Brief ~10m vs. ⚡ Rapid Fire @ 1.1x).
    - Upgraded sample brief player with jewel amber play button and progress track.
    - Added category-colored accent dots to topic selection rows and introduced "Skip for now" to support guest listening without blocking setup.
  - **Screen Layout & Viewport Optimization**:
    - Replaced the oversized notice banner with a compact 36dp pill (`Showing latest brief` with inline actions).
    - Reduced hero deck height by >150dp: streamlined 32dp edition selector that prevents line wrapping, 48dp audio art tile, and a collapsible Read-Along visor.
    - Story cards now sit comfortably above the fold on all standard mobile screens without getting buried.
  - **Story Card Refinement**:
    - Added a 2-line summary preview when cards are collapsed, mirroring the PWA `.story-snippet` for quick skimming.
    - Added category-tinted play tiles (38dp) with category color accent and play/soundwave indicator.
    - Eliminated duplicate section title labels within card headers.
    - Full drawer expansion reveals complete summary, source attributions, external article link, and report button.
  - **Public Briefing Access**:
    - Fixed public briefing queries (`storyAudio`, `latestStoryDate`, `voiceNotes`) to allow unauthenticated/guest listeners to stream public daily packs without authentication errors.

---

## [0.1.45] - 2026-10-22

### Changed
- **Android App UI & Feature Parity with Hark Daily PWA Overhaul**:
  - **Acoustic Studio Deck Hero**:
    - Replaced the legacy player card with an elevated Hi-Fi Acoustic Studio Deck featuring an amber sunburst top horizon bar (3.5dp), ambient warm glow during playback, tactile jewel amber play button, and recessed console deck (`#0B0F17` in dark mode).
    - Integrated Read-Along Teleprompter Visor directly beneath the console deck with live narrator text tracking and full text expand/collapse.
    - Updated app header branding to "Hark Daily" with tagline "The news you hear, not just read."
  - **⚡ Rapid Fire Mode on Android**:
    - Added instant switcher between **Full Brief** (~10 min) and **⚡ Rapid Fire** (Top 5 stories @ 1.1x speed).
    - Rapid Fire curates the top 5 stories of the day, sets playback speed automatically to 1.1x, and updates transport speed pills with `1.1x` option.
  - **Editorial Broadsheet Story Cards**:
    - Distinct story cards with 4dp category colored left spine (`t.categoryColor(card.section)`).
    - Amber accent border and ambient shadow when story is playing.
    - Upgraded progress bar and scrubbers with warm amber track fill and jewel thumb.
    - Bottom MiniPlayer and TabBar updated with Hark Daily amber accent highlights and tactile jewel play button.

---

## [0.1.44] - 2026-10-19

### Changed
- **UI Design Overhaul: Acoustic Studio Deck vs. Editorial Broadsheet**:
  - **News Player (`.hero`)**: Redesigned as an elevated Hi-Fi Acoustic Studio Deck featuring an amber sunburst top horizon bar (`border-top: 3.5px solid var(--accent)`), ambient radial warmth, a tactile jewel sunburst play button, seamless recessed waveform deck, and a teleprompter-styled Read Along prompter.
  - **Dark Mode Separation**: Solved dark mode sameness by styling the player as a deep obsidian console (`#131926` to `#0c1018`) with amber glow, while news articles elevate to crisp slate tiles (`#141c2c`) with `#f8fafc` typography.
  - **Editorial News Cards (`.story-row`)**: Introduced vibrant 4px category accent spines (`border-left: 4px solid var(--cat)`), interactive hover elevation, and vivid amber edge-glow during playback.
  - **Duplicate Text & Read-Along Polish**:
    - Eliminated duplicate section text in the player kicker (no more `[PAUSED · TOP STORIES] · TOP STORIES`).
    - Fixed duplicate snippet text when expanding story details (snippet cleanly yields to the full summary drawer).
    - Replaced clunky orange focus boxes in Read-Along with word-level amber typography glow and crisp contrast tracking.
  - Service worker cache bumped to `hark-daily-v7`.

---

## [0.1.43] - 2026-10-19

### Changed
- **⚡ Rapid Fire Rethink (Top 5 Stories @ 1.1x speed)**:
  - Curates all 5 top stories of the day from the Top Stories section (rather than 1 clip per section).
  - Automatically speeds up audio narration to **1.1x** in Rapid Fire mode for a punchy, brisk headline delivery.
  - Dynamic transport speed pills automatically display and highlight the `1.1x` option when in Rapid Fire mode, while preserving standard speed settings for Full Edition.
  - Mode-specific playback position memory prevents position collisions between Full Edition and Rapid Fire.
  - Service worker cache bumped to `hark-daily-v6`.

---

## [0.1.42] - 2026-10-19

### Added
- **⚡ Rapid Fire Mode (90-second speed run)**:
  - Instant client-side edition switching between **Full Brief** (~10 min) and **Rapid Fire** (⚡ 90s) with zero server generation or GPU cost.
  - Curates top-ranked story clips across the listener's first four active sections without intro delays.
  - Tactile segmented edition switcher on the home screen hero player card with real-time lineup and duration updates.
  - Preferred edition selector integrated into the first-run onboarding Welcome Sheet.
- **Continuous Lock-Screen Audio (Android PWA & iOS Safari)**:
  - Refactored audio playback engine to use a single persistent in-DOM `<audio>` element, preventing Android Chrome and iOS WebKit background audio focus revocation when advancing chapters.
  - Headless background clip preloading into HTTP cache for seamless, gapless track transitions.
  - Added `navigator.mediaSession.setPositionState` synchronization for accurate lock-screen scrubbers across multi-clip briefings.

### Changed
- **Default Appearance to Light Mode**:
  - Application theme now defaults to clean, warm paper Light Mode across the web app, landing page, and legal pages.
  - Service worker cache bumped to `hark-daily-v5`.

---

## [0.1.41] - 2026-10-18

### Added
- **GPU Cost Safeguards & Verified Shutdown**:
  - Automatic verified VM shutdown on every exit path, even if the VM was already running before the session.
  - Hypervisor-level 90-minute `max-run-duration` with `instance-termination-action=STOP` on GCP.
  - Multi-attempt verified stopping with Compute Engine status polling.
- **Pipeline Resilience & Narrator Isolation**:
  - Per-narrator error isolation in `storypack.build`: completed narrators are preserved and published even if another narrator fails.
  - Internal `--deadline` parameter stops scheduling new clips cleanly before container timeouts occur.
  - Automatic retry for transient 429/502/503/504/520–524 HTTP errors in Supabase storage and database calls.
  - Cross-process distributed lease locking (`public.pack_lease`) prevents conflicting runs from hitting the GPU simultaneously.
- **Performance Optimizations**:
  - Pipelined clip uploads: audio uploads to Supabase Storage asynchronously in background threads while the next clip synthesizes.
  - Framing notes carry-over: reuses identical greetings and section intros from the previous day via Storage copy without re-voicing (saving 44 clips / ~8 min).
- **Automation & Scheduling**:
  - Cloud Run `morning-brief-pack` job configured with 60m timeout, 50m deadline, and 0 retries to prevent runaway billing.
  - Added secondary safety-net job `morning-brief-report` at 06:15 AM to verify completeness, retry missing narrators, and alert admins.
  - Persistent VAPID keys passed to Cloud Run containers, eliminating ephemeral key churn and 403 push notification errors.
  - Thread-safe voice conditioning in Chatterbox-Turbo TTS engine.

---

## [0.1.40] - 2026-10-18

### Changed
- **C-3PO is the default narrator** for the landing preview and for new accounts (`DEFAULT_VOICE_ID`). The voice a visitor hears first carries into their account. Web service worker cache is now `morning-brief-v45`.

---

## [0.1.39] - 2026-10-18

### Changed
- **Web onboarding no longer forces sign-in**: "Start your brief" plays today's top 2 stories in the chosen narrator, with voice chips (Alice, Mike, Jerry, C-3PO). A "Keep listening" prompt follows, and the chosen voice carries into the new account.
- The pack publishes a landing sample per narrator (`showcase/sample-<voice>.json`), top 2 stories only. The checked-in `web/sample` bundle is removed.
- Web service worker cache bumped to `morning-brief-v44`.

---

## [0.1.35] - 2026-10-10

### Added
- **4 Distinct Neural Narrators**: Added full support and pre-rendered story packs for:
  - 🤖 **C-3PO** (`c3po_reference`) — Polite, precise protocol droid voice style.
  - 🎙️ **Jerry** (`jerry_reference`) — Observational wit and dynamic commentary.
  - 📻 **Alice** (`her_reference`) — Warm British newsreader.
  - 🎙️ **Mike** (`him_reference`) — Crisp American morning news anchor.
- **Anytime-of-Day Greetings**: Dynamic time-based greetings (`Good morning`, `Good afternoon`, `Good evening`) pre-voiced for every narrator to support morning, midday, and evening listening.
- **Transparent Web Fallback & Availability Indicators**:
  - Web client tracks `availableVoices` per briefing date.
  - Narrator picker sheet displays `Pending` badges for voices that haven't yet rendered for a given day.
  - Player honestly notifies listeners if an unrecorded voice was requested and fell back to an active narrator.
- **Automated GCE GPU Lifecycle**: Worker automatically starts the NVIDIA L4 GPU VM (`morning-brief-voice`) on GCE, renders story audio, and unconditionally halts the VM to prevent idle compute costs.
- **Voice Studio & Audio Tooling**: Added 24kHz audio formatter and reference audio synchronizer (`scripts/sync-voices-to-gce.sh`).

### Fixed
- **Android App**:
  - Gated the "your last brief couldn't be made" error banner exclusively to admin accounts.
  - Gracefully fallback to any pre-existing cached briefing for standard listeners.
  - Added auto-timeout dismiss behavior for transient error banners.
- **Cloud Run Batch Worker**:
  - Configured `STORY_VOICES` environment variable explicitly across Google Cloud Run and Cloud Scheduler to voice all 4 narrators every morning at 05:00 AM.
  - Fixed audio generation pipeline to prevent dropping voices during scheduled runs.

---

## [0.1.34] - 2026-10-10

### Added
- **PWA v2 UI Redesign**: Modern frosted-glass aesthetic with compact mobile headers, continuous scrub bars, and circular button invariants.
- **Integrated Read-Along Mode**: Live transcript auto-scrolling with synchronized chapter and story card highlights.
- **Compact Narrator Switcher**: Bottom sheet drawer for rapid 1-tap switching between voice personas.

### Fixed
- **Read-Along Truncation**: Fixed transcript clipping and scroll sync across iOS Safari, iPadOS, and Android Chrome.
- **Player Geometry**: Resolved squished play/pause button states on narrow mobile viewports.

---

## [0.1.33] - 2026-10-09

### Added
- **Spoken Outro Sign-off**: Added a polite closing note (`outro`) after the final story so briefings do not terminate abruptly.
- **Freshness & Archive Indicators**: Added visual pills distinguishing today's sunrise edition from older archived editions.

### Fixed
- **Pack Completeness Gate**: PWA and Android clients strictly enforce `pack_ready` marker verification before playing, preventing partial or mixed-voice briefings mid-render.

---

## [0.1.30 - 0.1.32] - 2026-10-08

### Added
- **Single-Source Guardian Shared Story Pack**: Switched primary daily briefing generation to The Guardian's 7 official editorial categories (`top`, `ai`, `tech`, `politics`, `entertainment`, `science`, `sports`).
- **Extractive Algorithmic Summarizer**: Integrated `trafilatura` article extraction with TF-based lead-paragraph summarization, eliminating LLM hallucinations and rate limits for daily news.
- **0.8s Breath Intervals**: Inserted natural silent audio pauses (`gap.mp3`) between stories and chapter intros to prevent abrupt sentence collisions.
- **Admin Audio Dashboard**: Added real-time monitoring and rebuild controls for published audio packs.

---

## [0.1.18 - 0.1.25] - 2026-10-06

### Added
- **3-Step Welcome Onboarding**: Streamlined first-run experience for topic selection and voice preference.
- **Story Photos Toggle**: Added support for high-resolution color lead photography on story cards.
- **Multi-Provider AI Fallback**: Added support for Bring-Your-Own-Key (BYOK) AI summaries via Google Gemini (Gemini 2.5/3 Flash), Groq, and OpenRouter for custom RSS sources.
- **Cloud Run Deployment**: Containerized batch worker deployed to Google Cloud Run with Cloud Scheduler triggers.

---

## [0.1.0 - 0.1.17] - 2026-10-01

### Added
- **Initial Native Android App**: Jetpack Compose application with Android Media3 background playback, lock-screen controls, and notification integration.
- **Web Progressive Web App (PWA)**: Desktop and mobile PWA with offline caching and responsive light/dark themes.
- **Supabase Backend**: User authentication (Google OAuth & magic links), profile settings sync, and Storage bucket for audio clips.
- **Account Management**: Self-service account deletion cascading through all user data and audio links.
