# Continuous Audio Playback & Transition Discipline

Mobile web browsers (iOS Safari, Android Chrome) and native hybrid WebViews (Capacitor/WebView) enforce strict media autoplay, background execution, and audio decoding lifecycles. Any regressions that cause audio to stall, stutter, or pause abruptly degrade the core user experience.

Always follow these rules when modifying the player (`web/js/player.js`), playlist queue (`web/js/storypack.js`), or service worker (`web/sw.js`):

## 1. Respect the Transition Lock (`isTransitioningClip`)
- Setting `<audio>.src` or invoking `<audio>.load()` while media was playing causes browsers to dispatch a synchronous or microtask `pause` event before buffering new metadata.
- **Never** reset `this.isTransitioningClip = false` before `el.src` changes or `el.load()` executes when transitioning between sequential clips.
- Keep `this.isTransitioningClip = true` across the clip swap, releasing it only when `play` or `playing` fires or when the `el.play()` promise settles.
- If `pause` fires while `this.isTransitioningClip` is true, ignore it — never call `setPlaying(false)`, release wake locks, or notify native Android / MediaSession of a pause.
- Back up the transition with a safety timeout (e.g. 5s) so the lock cannot stay set indefinitely if a stream hangs.

## 2. No Artificial Short Audio Gaps in Podcast Mode
- **Never** inject artificial short audio clips (`gap.mp3`, `separator.mp3`, etc.) between stories or banter in podcast mode (`if (isPodcast) return;`).
- In mobile Android and iOS, sequential transitions through ultra-short audio files (< 2 seconds) cause media decoders, Android `AudioTrack`, and `MediaSession` to treat the stream as underrun or finished, halting playback or dropping foreground playback services.
- The podcast briefing flows naturally and continuously across real voice audio clips: host opening banter, section teasers, section bridges, and two-host conversational stories.
- Every clip in `clips` must map directly to an entry in `chapters` with valid metadata, avoiding desynchronization between chapter tracking and playback indices.

## 3. Preloader Hygiene & Seamless Transition
- The secondary preloader (`#audioB`) silently pre-buffers the next upcoming story MP3 in the user's browser cache.
- When `#audio` loads a clip that `#audioB` was preloading, pause and detach `#audioB` so the two elements do not contend on the same byte ranges or socket connections.
- Skip gaps and ultra-short non-story clips in `preloadNext()` to avoid preloading ephemeral clips.

## 4. Avoid Redundant Zero-Seeks
- Setting `el.currentTime = 0` on a freshly loaded audio element triggers redundant seek pipelines in WebKit and Blink, causing decode stalls and transient pauses.
- Only attach `applySeek` / `loadedmetadata` seek listeners when `seek > 0`.

## 5. Fail-Safe Auto-Advance on Transition Audio Errors
- If a section bridge, banter, or gap clip fails to decode or rejects `play()`, immediately catch and advance to `this.index + 1` so the news briefing never halts before a category.
