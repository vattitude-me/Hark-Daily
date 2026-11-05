# Release Notes

## [v1.0.11] - 2026-11-04

### 🚀 New Features
- **Capacitor 8 Mobile Smart Shells (Android & iOS)**:
  - Finalized Android build system with OpenJDK 21 auto-detection, verified signed release APK (`hark-daily-1.0.11.apk`) and Google Play App Bundle (`hark-daily-release.aab`).
  - Added modern iOS Capacitor 8 platform using Swift Package Manager (SPM); configured `AVAudioSession` `.playback` category with `.spokenAudio` mode for background playback on Lock Screen, Control Center, Dynamic Island, and CarPlay.
  - Added `UIBackgroundModes` (`audio`, `fetch`, `remote-notification`), custom URL scheme (`me.vattitude.morningbrief://`), 1024×1024 Universal AppIcon, and 2732×2732 launch splash assets.
- **Briefing Restart Support**:
  - Added one-tap "Restart briefing" from beginning in the hamburger drawer settings.
  - Previous chapter button (`prevChapter()`) automatically seeks to `0:00` if pressed on story 1 or within the first 3 seconds of a brief.
- **NAS Watchdog Sentinel & Discord DR Monitoring**:
  - Automated sentinel script deployed to always-on Linux NAS (`10.0.0.233`) with Discord rich embeds and Wake-on-LAN recovery packets to the Mac producer.

### ⚡ Improvements
- **Hamburger Drawer Action Bar Overhaul**:
  - Clean default state: displays only a single full-width **"Close"** button by default.
  - Dynamic staged state: smoothly morphs into **"Discard"** and **"Save changes"** when an edition or setting is modified, eliminating accidental saves.

### 🐛 Bug Fixes
- **Deep Hardware Audio Decoder & Pipeline Reset**:
  - Enforced full audio pipeline flush (`pause()`, `removeAttribute('src')`, `load()`, preloader purge) on edition switch, clearing browser hardware audio buffers so previous edition audio never bleeds into new regions.
- **Strict Per-Edition Caching**:
  - Isolated cache keys by edition (`last-briefing-ca`, `last-briefing-us`, `last-briefing-in`).
  - Prevented stale Canadian stories from optimistically painting or playing when India or US is selected.
