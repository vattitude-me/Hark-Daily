<div align="center">

<img src="docs/play-store/feature-graphic.png" alt="Hark Daily" width="100%" style="border-radius: 16px; margin-bottom: 20px;" />

# 🎙️ Hark Daily

**The news you hear, not just read.**  
A concise daily audio briefing covering **Canada**, the **United States**, and **India** from **CBC News**, **The New York Times**, **NPR**, **The Hindu**, **The Indian Express**, **TechCrunch**, **ScienceDaily**, and **ESPNcricinfo**. Voiced by a duo-host neural podcast team (Matthew & Kelly) alongside solo narrator personas.  
No ads. Fast audio briefings. Zero doom-scrolling. 24-hour listening.

[![Web PWA](https://img.shields.io/badge/Web-Live_Demo-2f6fed?style=flat-square&logo=googlechrome&logoColor=white)](https://hark.vattitude.ca)
[![Android App](https://img.shields.io/badge/Android-APK_v1.0.3-1a9b5b?style=flat-square&logo=android&logoColor=white)](https://github.com/vattitude-me/Hark-Daily/releases/tag/android-v1.0.3)
[![Neural Voice](https://img.shields.io/badge/Voice-Chatterbox--Turbo-6a4cf5?style=flat-square)](voice_service/)
[![Changelog](https://img.shields.io/badge/Changelog-v1.0.7-orange?style=flat-square)](CHANGELOG.md)
[![Privacy First](https://img.shields.io/badge/Privacy-No_Ads_%7C_Privacy_First-0D0D0D?style=flat-square)](web/privacy.html)

[**Web PWA**](#-web-pwa) · [**Android App**](#-android-app) · [**Features**](#-features) · [**Privacy**](web/privacy.html) · [**Terms**](web/terms.html) · [**Changelog**](CHANGELOG.md) · [**Technical Guide**](docs/TECHNICAL.md)

</div>

---

## ☕ Features

* **Duo-Host AI Podcast (Default)**: Matthew & Kelly break down the day's stories in a natural two-host dialogue. Host 1 introduces the headline and context; Host 2 adds the angle, implication, and takeaway. Natural banter, section teases, and zero canned laughs.
* **Full Brief Mode**: Prefer a solo news anchor? Switch to continuous radio-style narration voiced by C-3PO or chosen neural personas.
* **Multi-Country Editions (🇨🇦 Canada, 🇺🇸 US, 🇮🇳 India)**:
  * 🇨🇦 **Canada** — CBC News (Top, Politics, Arts, Sports) & BetaKit (Tech).
  * 🇺🇸 **United States** — The New York Times (Top), NPR Politics, Variety (Entertainment), CBS Sports.
  * 🇮🇳 **India** — The Hindu (Top/National), The Indian Express (Politics, Arts), ESPNcricinfo (Cricket/Sports).
  * 🌐 **Global Universals** — TechCrunch (AI), BetaKit/Verge (Tech), ScienceDaily (Science). Voiced once and shared across all editions.
* **Pull-Down-to-Refresh**: Tactile pull gesture on both the Web PWA and Android app to check for updated packs and fresh editions on demand.
* **Pinned Player Bar**: 40-bar acoustic waveform scrubber and media transport stay locked to the viewport on any screen size, orientation change, or virtual keyboard shift.
* **Read-Along Teleprompter**: Spoken text highlights in real time with host badges (Matthew in amber, Kelly in teal). Tap any sentence to seek directly to that moment.
* **Time-Neutral 24-Hour Listening**: Broadcast scripts avoid time-locked morning phrases. Listen at 7:00 AM, 2:00 PM, or 11:00 PM without hearing stale morning greetings.
* **Instant Edition Switcher**: Auto-detects local edition from timezone with a 0ms topbar switcher (`🇨🇦 CA`, `🇺🇸 US`, `🇮🇳 IN`).
* **Deep-Link Story Sharing**: Share any story card via direct link (`?story={section}-{rank}&date={YYYY-MM-DD}`). Receivers land directly on the shared audio clip.
* **Two-Tier Daily Synthesis**:
  * **Morning Batch (~6:00 AM EDT)**: Synthesizes Canada & US local sections + universal AI, Tech, Science.
  * **Evening Batch (~6:00 PM EDT / 3:30 AM IST)**: Synthesizes India local sections ahead of Indian morning commute while reusing today's universal AI, Tech, and Science audio.
* **Local Apple Silicon Synthesis**: Runs on macOS via PyTorch Metal Performance Shaders (MPS) and automated `launchd` scheduling. Zero cloud GPU costs.
* **Zero Accounts, Zero Ads**: Open [hark.vattitude.ca](https://hark.vattitude.ca) and hit play. No sign-up required, no paywalls, and no sponsored feeds.

---

## 🖥️ Web PWA

Works across desktop, tablet, and mobile browsers with background playback, offline caching, and zero forced login.

<div align="center">

### Mobile PWA (Podcast Duo Mode, Topic Selector & Drawer)
<p align="center">
  <img src="docs/screenshots/clean-player-podcast.png" alt="Hark Daily Podcast Player" width="260" style="border-radius: 20px; box-shadow: 0 14px 40px rgba(0,0,0,0.5); margin: 8px;" />
  <img src="docs/screenshots/clean-player-topics.png" alt="Hark Daily Topic Selector" width="260" style="border-radius: 20px; box-shadow: 0 14px 40px rgba(0,0,0,0.5); margin: 8px;" />
  <img src="docs/screenshots/clean-player-menu.png" alt="Hark Daily Menu & Drawer" width="260" style="border-radius: 20px; box-shadow: 0 14px 40px rgba(0,0,0,0.5); margin: 8px;" />
</p>

### Desktop View (Today's Briefing & Podcast Player)
<img src="docs/screenshots/web-desktop-dark.png" alt="Hark Daily Web Desktop" width="100%" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); margin-bottom: 16px;" />

</div>

Install as a Progressive Web App (PWA) on Chrome, Edge, or Safari for background audio playback, offline caching, and home screen launch.

---

## 📱 Android App

Native Android application built with Jetpack Compose, Compose Material3 tokens, and Media3 background audio.

<div align="center">

| Active Playback | Today's Briefing | Story Feed | Topics & Sources |
| :---: | :---: | :---: | :---: |
| <img src="docs/screenshots/android-playing.png" width="200" alt="Android Playing" /> | <img src="docs/screenshots/android-today.png" width="200" alt="Android Today" /> | <img src="docs/screenshots/android-feed.png" width="200" alt="Android Story Feed" /> | <img src="docs/screenshots/android-sources.png" width="200" alt="Android Sources & Topics" /> |

</div>

- **Pull-Down-to-Refresh**: Smooth native pull gesture to refresh stories and audio packs on demand.
- **Background Playback**: Android Media3 notification and lock-screen playback controls with scrubber.
- **Narrator Switcher**: Instant switching between active voice personas without losing playback position.
- **Custom Category Sorting**: Prioritize and toggle categories according to your daily routine.
- **Device & Cloud Playback**: Stream cloud-voiced editions or run on-device audio offline.

---

## 🚀 Getting Started

### Web
1. Open the live web app at [**hark.vattitude.ca**](https://hark.vattitude.ca) (or local [web/](web/)).
2. Click **Play** on today’s edition—no account or sign-up required.
3. Switch your country edition anytime via the topbar flag chip (`🇨🇦 CA`, `🇺🇸 US`, `🇮🇳 IN`).
4. Pull down anytime on mobile to refresh today's briefing.
5. Tap voice chips in the drawer to audition and switch personas.

### Android
1. Download the latest signed APK from [GitHub Releases](https://github.com/vattitude-me/Hark-Daily/releases).
2. Install on any device running Android 10+ (API 29+).
3. Select your country edition and voice narrator in Settings, then start listening.

### Command-Line CLI Operations
```bash
# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Voice today's briefing pack for specific country editions
python -m app pack --edition ca,us       # Morning batch (Canada + US)
python -m app pack --edition in          # Evening batch (India morning peak)
python -m app pack --edition ca,us,in    # All three editions simultaneously

# Check completeness of today's pack across all voices
python -m app pack --check

# Dry-run / showcase landing sample only
python -m app pack --showcase-only
```

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

Free · Open Source · No ads · Privacy First

</div>
