<div align="center">

<img src="docs/play-store/feature-graphic.png" alt="Hark Daily" width="100%" style="border-radius: 16px; margin-bottom: 20px;" />

# 🎙️ Hark Daily

**The news you hear, not just read.**  
A concise daily audio briefing from **CBC News**, **TechCrunch**, **ScienceDaily**, and **BetaKit**, voiced by neural personas anchored by flagship narrator **C-3PO** alongside modular neural voices.  
No ads. No tracking. Zero doom-scrolling.

[![Web PWA](https://img.shields.io/badge/Web-Live_Demo-2f6fed?style=flat-square&logo=googlechrome&logoColor=white)](https://hark.vattitude.ca)
[![Android App](https://img.shields.io/badge/Android-APK_v0.1.69-1a9b5b?style=flat-square&logo=android&logoColor=white)](https://github.com/vattitude-me/Hark-Daily/releases/tag/android-v0.1.69)
[![Neural Voice](https://img.shields.io/badge/Voice-Chatterbox--Turbo-6a4cf5?style=flat-square)](voice_service/)
[![Changelog](https://img.shields.io/badge/Changelog-v0.1.69-orange?style=flat-square)](CHANGELOG.md)
[![Privacy First](https://img.shields.io/badge/Privacy-No_Ads_%7C_No_Tracking-0D0D0D?style=flat-square)](web/privacy.html)

[**Web PWA**](#-web-pwa) · [**Android App**](#-android-app) · [**Features**](#-features) · [**Privacy**](web/privacy.html) · [**Terms**](web/terms.html) · [**Changelog**](CHANGELOG.md) · [**Technical Guide**](docs/TECHNICAL.md)

</div>

---

## ☕ Features

* **Curated News Sources**: Verified reporting from CBC News, ScienceDaily, TechCrunch, and BetaKit across 7 categories (Top, AI, Tech, Politics, Entertainment, Science, Sports).
* **Neural Voices**: Voiced by C-3PO alongside co-hosts Matthew & Kelly via local Chatterbox-Turbo TTS.
* **Instant Playback**: Listen immediately on the web at [hark.vattitude.ca](https://hark.vattitude.ca) without sign-up.
* **Two Listening Modes**:
  * **Podcast (Default)** — Duo-host conversation with Matthew & Kelly tailored to your selected topics, with natural cadence, pauses, and broadcast titles.
  * **Full Brief** — Continuous radio-style narration across all chosen stories.
* **Time-Adaptive Greetings**: Adapts greeting audio (`Good morning`, `Good afternoon`, `Good evening`) to your local clock.
* **Cached Static Audio**: Reusable intros and sign-offs are stored permanently in Supabase, saving synthesis time on each batch.
* **Read-Along Teleprompter**: Subtitles and story cards follow the narrator in real time. Tap any card to seek to it.
* **Pull-to-Refresh**: Native pull gesture on Android to check for fresh editions on demand.
* **Custom Lineup**: Reorder topics and toggle categories to build your personal lineup.
* **Local Apple Silicon Synthesis**: Runs locally on macOS with PyTorch Metal Performance Shaders (MPS) and automated `launchd` scheduling. Zero cloud GPU costs.
* **No Ads or Tracking**: No sponsored stories, tracking pixels, or algorithmic feeds.

---

## 🖥️ Web PWA

Works in any modern browser on desktop, tablet, and mobile with automatic light and dark themes.

<div align="center">

### Desktop View (Light & Dark)
<img src="docs/screenshots/web-desktop-light.png" alt="Hark Daily Web Desktop Light Mode" width="100%" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-bottom: 16px;" />

<img src="docs/screenshots/web-desktop-dark.png" alt="Hark Daily Web Desktop Dark Mode" width="100%" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);" />

### Mobile Web PWA
<img src="docs/screenshots/web-mobile-light.png" alt="Hark Daily Web Mobile View" width="360" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-top: 12px;" />

</div>

Install as a Progressive Web App (PWA) on Chrome, Edge, or Safari for offline caching, background playback, and web push notifications.

---

## 📱 Android App

Native Android application built with Jetpack Compose, Compose Material3 tokens, and Media3 background audio.

<div align="center">

| Today's Briefing | Follow-Along Audio | Topics & Sources | Settings & Voices |
| :---: | :---: | :---: | :---: |
| <img src="docs/screenshots/android-today-light.png" width="220" alt="Android Today Light" /> | <img src="docs/screenshots/android-playing-dark.png" width="220" alt="Android Playing Dark" /> | <img src="docs/screenshots/android-sources-light.png" width="220" alt="Android Sources Light" /> | <img src="docs/screenshots/android-settings-light.png" width="220" alt="Android Settings Light" /> |

</div>

- **Pull-Down-to-Refresh**: Smooth native pull gesture to refresh stories and audio packs on demand.
- **Background Playback**: Android Media3 notification and lock-screen playback controls with scrubber.
- **Narrator Switcher**: Instant switching between active voice personas without losing playback position.
- **Custom Category Sorting**: Prioritize and toggle categories according to your morning routine.
- **Device & Cloud Playback**: Stream cloud-voiced editions or run on-device audio offline.

---

## 🚀 Getting Started

### Web
1. Open the live web app at [**hark.vattitude.ca**](https://hark.vattitude.ca) (or local [web/](web/)).
2. Click **Play** on today’s edition—no account or sign-up required.
3. Tap the voice chips in the player to audition and switch narrators on the fly.
4. Sign in with Google or magic link if you wish to sync custom topic preferences across devices.

### Android
1. Download the latest signed APK from [GitHub Releases](https://github.com/vattitude-me/Hark-Daily/releases).
2. Install on any device running Android 10+ (API 29+).
3. Select your preferred voice narrator in Settings and start listening.

---

## 🛠️ Developer Documentation

- [**Technical & Architecture Guide (`docs/TECHNICAL.md`)**](docs/TECHNICAL.md) — Architecture diagrams, Supabase schema, Apple Silicon MPS pipeline, and dual-edition power relay.
- [**Automated Daily Pack Run Guide (`docs/nightly.md`)**](docs/nightly.md) — macOS launchd automation, sleep/wake power management, and manual CLI operations.
- [**Android App Guide (`android/README.md`)**](android/README.md) — Gradle build steps, Compose architecture, and release signing.
- [**Voice Service Guide (`voice_service/README.md`)**](voice_service/README.md) — Chatterbox-Turbo TTS service, FastAPI endpoints, GPU acceleration, and voice reference clips.
- [**Privacy Policy (`web/privacy.html`)**](web/privacy.html) — Clear statement on data minimization and privacy.
- [**Terms of Use (`web/terms.html`)**](web/terms.html) — Fair dealing and source attribution terms.
- [**Changelog (`CHANGELOG.md`)**](CHANGELOG.md) — Version history and release notes.

---

<div align="center">

Free · Open Source · No ads · No tracking

</div>
