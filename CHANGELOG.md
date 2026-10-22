# Changelog

All notable changes to the **Morning Brief** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
