# Continuous Audio Playback & Transition Discipline

Mobile web browsers (iOS Safari, Android Chrome) and native hybrid WebViews (Capacitor/WebView) enforce strict media autoplay, background execution, and audio decoding lifecycles. Any regressions that cause audio to stall, stutter, or pause abruptly degrade the core user experience.

Always follow these rules when modifying the player (`web/js/player.js`), playlist queue (`web/js/storypack.js`), or service worker (`web/sw.js`):

## 1. Respect the Transition Lock (`isTransitioningClip`)
- Setting `<audio>.src` or invoking `<audio>.load()` while media is playing causes the browser to fire a synchronous or microtask `pause` event before loading new metadata.
- **Never** reset `this.isTransitioningClip = false` before `el.src` changes or `el.load()` completes when transitioning between sequential clips.
- Keep `this.isTransitioningClip = true` across the clip swap, clearing it only when `play` / `playing` fires or when the `el.play()` promise settles.
- If `pause` fires while `this.isTransitioningClip` is true, ignore it — never call `setPlaying(false)`, release wake locks, or notify native Android/MediaSession of a pause.

## 2. Queue Construction & Acoustic Separators
- Separator clips (`separator.mp3`) represent the end of an article/story. They must **only** be placed after a story has finished (`storyPlayed`).
- **Never** insert separators between opening conversational banter (e.g. `open` → `teasers`).
- **Never** insert a separator between a section bridge (e.g. `"Moving over to AI. Here's what's happening."`) and the first story of that section. The bridge introduces the story and flows straight into it.
- **Never** permit consecutive `gap` clips in the queue.

## 3. Preloader Channel Hygiene
- The secondary preloader (`#audioB`) must only pre-buffer upcoming *story* clips (`clips.slice(this.index + 1).find(c => !c.gap)`).
- Never set `#audioB.src` to a 1.2-second static separator clip (`separator.mp3`), as this causes simultaneous decoding/fetch contention on the same URL between `#audio` and `#audioB`.

## 4. Cache Static Shell Audio
- Static audio bundled in the app shell (`/audio/separator.mp3`, `/audio/gap.mp3`) must be served directly from the Service Worker cache (`isStatic`) and exempted from dynamic `.mp3` bypass rules.

## 5. Avoid Redundant Zero-Seeks
- Setting `el.currentTime = 0` on a freshly loaded audio element triggers redundant seek pipelines in WebKit and Blink.
- Only attach `applySeek` / `loadedmetadata` seek listeners when `seek > 0`.

## 6. Fail-Safe Auto-Advance on Gap Errors
- Separator chimes are non-critical aesthetic dividers.
- If a `gap` clip fails to decode, errors out, or rejects `el.play()`, immediately catch and advance to `this.index + 1` so the news briefing never stalls.
