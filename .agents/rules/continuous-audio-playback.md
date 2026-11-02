# Continuous Audio Playback & Transition Discipline

Mobile web browsers (iOS Safari, Android Chrome) and native hybrid WebViews (Capacitor/WebView) enforce strict media autoplay, background execution, and audio decoding lifecycles. Any regressions that cause audio to stall, stutter, or pause abruptly degrade the core user experience.

Always follow these rules when modifying the player (`web/js/player.js`), playlist queue (`web/js/storypack.js`), or service worker (`web/sw.js`):

## 1. No Artificial Short Audio Gaps in Podcast Mode
- **Never** inject artificial short audio clips (`gap.mp3`, `separator.mp3`, etc.) between stories or banter in podcast mode (`if (isPodcast) return;`).
- In mobile Android and iOS, sequential transitions through ultra-short audio files (< 2 seconds) cause media decoders, Android `AudioTrack`, and `MediaSession` to treat the stream as underrun or finished, halting playback or dropping foreground playback services.
- The podcast briefing flows naturally and continuously across real voice audio clips: host opening banter, section teasers, section bridges, and two-host conversational stories.
- Every clip in `clips` must map directly to an entry in `chapters` with valid metadata, avoiding desynchronization between chapter tracking and playback indices.

## 2. Preloader Hygiene & Seamless Transition
- The secondary preloader (`#audioB`) silently pre-buffers the next upcoming story MP3 in the user's browser cache.
- When `onEnded` fires on `#audio`, `#audio` immediately loads and plays the next clip without intermediate artificial pauses or gap audio files.

## 3. Avoid Modifying Stable Playback Pipelines
- Do not introduce synchronous state disruptions, fake transition intervals, or simulated loading audio clips into the production player loop. Keep the audio queue 100% focused on real content tracks.
