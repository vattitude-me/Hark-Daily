# Social Media Announcements

## [v1.0.11] - 2026-11-04

### LinkedIn

We are excited to announce Hark Daily v1.0.11! 🎙️

Hark Daily delivers a personalized, AI-voiced morning news brief curated from top trusted publications. In this release, we have significantly expanded our mobile platform experience with modern native smart shells for both Android and iOS powered by Capacitor 8.

Key highlights in v1.0.11:
• Native Mobile Shells: Android production build finalized with signed APKs and AAB bundles; iOS platform added with AVAudioSession background audio support across Lock Screen, Control Center, Dynamic Island, and CarPlay.
• Frictionless Drawer UX: Brand new modal footer action bar that stays clean with a single "Close" button and morphs dynamically to "Discard" and "Save changes" only when settings are edited.
• Audio Hardware Pipeline Reset: Seamless country edition switching (Canada, USA, India) with deep decoder flushes to prevent cross-region audio bleeding.
• Briefing Restart: Tap "Restart briefing" or hit previous on track 1 to start your morning news fresh from 0:00.

Check out the web app or grab the latest Android APK release on GitHub!
#OpenSource #MobileDev #AudioNews #Capacitor #Android #iOS #PWA #TechNews

---

### Reddit

**Subreddits**: r/webdev, r/androiddev, r/iosdev, r/opensource, r/SideProject

**Title**: Hark Daily v1.0.11: Bringing background audio, Capacitor 8, and multi-edition news to Android & iOS

**Post Body**:
Hey r/webdev and r/androiddev!

I’ve been building **Hark Daily** (https://hark.vattitude.ca), an open-source personalized audio morning brief voiced by an AI Duo (Matthew & Kelly) covering Canada, the US, and India editions across 7 categories.

Today we're releasing **v1.0.11**, which expands our web PWA into full **Capacitor 8 native smart shells** on both Android and iOS:

1. **Uninterrupted Background Playback**:
   - On Android: Foreground Service (`HarkMediaService`) with a CPU `PARTIAL_WAKE_LOCK` to prevent OS battery-saver suspension and thread freezing when the screen turns off.
   - On iOS: `AVAudioSession` set to `.playback` (`mode: .spokenAudio`) with `UIBackgroundModes` (`audio`, `fetch`, `remote-notification`), keeping audio alive on the lock screen, Control Center, and CarPlay.

2. **Mobile Web & Drawer UX Polish**:
   - Hamburger drawer footer now defaults to a single "Close" button. When a user taps a different region pill, the bar smoothly morphs into "Discard" + "Save changes".
   - Deep hardware audio decoder flush: when switching regions, we flush both primary and preloader `<audio>` elements (`removeAttribute('src')`, `load()`) to prevent the browser's hardware audio buffer from continuing to play the previous country's audio.
   - Strict per-edition localStorage caching (`last-briefing-ca`, `last-briefing-us`, `last-briefing-in`).

APK is attached to the GitHub release. Feedback on audio handling and hybrid native architecture is very welcome!

---

### X (Twitter)

Hark Daily v1.0.11 is out! 🎙️

📱 Android & iOS smart shells via Capacitor 8
🎧 Uninterrupted background audio on Lock Screen & CarPlay
🔄 Deep hardware audio flush on region switch
↺ One-tap briefing restart

Grab the signed APK on GitHub: https://github.com/vattitude-me/Hark-Daily/releases
