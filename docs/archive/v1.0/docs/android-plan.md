# Morning Brief on Android: on-device briefing plan

Oct 1, 2026 · Live version with diagrams: https://claude.ai/code/artifact/2063d2eb-9d69-490a-8f8e-def5175039f8

## Goal and scope

Ship an Android app that builds each user's morning briefing on their own phone, so the server worker stops being on the critical path for anyone using the app. The server keeps the jobs a phone can't do well or shouldn't repeat: accounts, the landing-page demo, and the web app for people without Android.

In scope for the first release:

- Fetch, rank, dedupe, summarize, script, voice and play the briefing entirely on the device.
- A scheduled build before the user's wake-up time, with a notification when it's ready.
- The phone's built-in voice by default; better voices as an optional download.
- Sign in with the same Google account, and sync sources and settings with the existing Supabase project.

Out of scope for now: iOS, Wear OS, Android Auto, and sharing briefings between users.

What stays on the server:

| Job | Where it runs after the app ships | Why |
| --- | --- | --- |
| Accounts, sources, settings | Supabase (unchanged) | One source of truth across web and Android |
| Web users' briefings | server worker (unchanged) | The web app has no way to build in the background |
| Landing-page demo | server worker, from the admin's briefing | Already built; needs a server build to exist |
| Android users' briefings | The phone | The point of this project |

## How the pipeline moves onto the phone

Every step of today's Python worker has an Android equivalent. The ranking, dedupe and script logic is plain code and ports to Kotlin almost line for line. Only voice and summaries need new technology.

| Step | Server today | On the phone | Effort |
| --- | --- | --- | --- |
| Fetch feeds | `fetcher.py`: httpx + feedparser, 6 feeds in parallel | OkHttp + coroutines; RSS/Atom parsed with Android's built-in XmlPullParser | Small |
| Read full articles | trafilatura | Readability4J (a Kotlin port of Mozilla Readability) on the downloaded HTML | Medium: extraction quality must be checked against trafilatura |
| Rank and group | `ranking.py`: token overlap, recency and position scores | Direct Kotlin port, same thresholds, shared test cases | Small |
| Dedupe across days | `ranking.py`: skips stories from the last two briefings | Same rules; history kept in a local Room database | Small |
| Summaries | Groq `gpt-oss-120b`, extractive fallback | See Summaries: on-device model where available, extractive port everywhere | Medium |
| Script | `writer.py` templates: intro, transitions, sign-off | Direct port of the templates | Small |
| Voice | Kokoro-82M or Edge voices, on the server CPU | Android's TextToSpeech by default; optional neural pack. See Voices | Medium |
| Assemble audio | numpy + lameenc, one MP3 with chapter marks | Concatenate the voice clips' PCM; MediaCodec encodes to AAC (.m4a), no MP3 library needed | Medium |
| Play | Web audio player | Media3 ExoPlayer in a MediaSessionService: lock screen, Bluetooth and headset buttons, chapter skip | Small |
| Notify | Web Push from the worker | A local notification when the build finishes; no push server involved | Small |

To keep the Python and Kotlin rankers from drifting apart, the server's test fixtures (`tests/fakenews.py` stories and their expected picks) become shared JSON fixtures that both test suites run.

## Voices

The app speaks with the phone's own text-to-speech engine out of the box, so a new user downloads nothing. Better voices are opt-in, in two steps: Google's high-quality offline voices first, then the same Kokoro voices the web app uses today.

| Tier | What it is | Download | Works offline | Who gets it |
| --- | --- | --- | --- | --- |
| 1. Phone default | Android `TextToSpeech`, usually Speech Services by Google | None | Yes, if the voice is installed | Everyone, on first run |
| 2. Google HD voices | Higher-quality voices in Speech Services by Google, installed from the system voice-data screen | Handled by Android, not by the app | Yes, once installed | Users who tap "Get better voices" |
| 3. Kokoro pack | Kokoro-82M run in the app through ONNX Runtime (sherpa-onnx), same voices as the web app | About 330 MB for the full model; an int8 build is smaller | Yes | Users who want the voice they already chose on the web |

How tiers 1 and 2 work:

- Each part of the script (intro, each story, transitions, sign-off) is rendered with `synthesizeToFile()` to a WAV clip, then the clips are joined. This is the same "voice each segment, then stitch" approach the server uses.
- The voice list comes from `getVoices()`. The app hides voices marked `KEY_FEATURE_NETWORK_SYNTHESIS` (they fail on a sleeping phone with no network) and flags ones marked `KEY_FEATURE_NOT_INSTALLED` as "download to use".
- "Get better voices" fires `ACTION_INSTALL_TTS_DATA`, which opens Android's own voice download screen. Google hosts and updates those voices, so this costs the app nothing.
- On Samsung and some other phones the default engine is the maker's, not Google's. When Speech Services by Google is installed, the app asks for it by package name, `com.google.android.tts`, rather than taking whatever the default is.
- The manifest needs a `<queries>` entry for the `android.intent.action.TTS_SERVICE` intent, or Android 11+ hides the engines from the app.

The Kokoro pack is a good fit for existing users: the voice IDs saved in their settings, such as `kokoro:af_heart`, keep working unchanged. The download goes over Wi-Fi only and can be deleted from Settings.

Sources: [TextToSpeech reference](https://developer.android.com/reference/android/speech/tts/TextToSpeech), [Kokoro-82M on Android](https://soniqo.audio/guides/kokoro/android).

## Summaries

The scheduled build uses the extractive summarizer ported from the server, with an optional downloaded Gemma model for better summaries. Gemini Nano is only used when the user rebuilds by hand with the app open, because Google blocks it in the background.

| Option | Runs in a scheduled background build | Download | Devices | Role |
| --- | --- | --- | --- | --- |
| Extractive summarizer (port of `summarizer.py`) | Yes | None | All | Default, and the fallback for everything else |
| Gemma 3 1B (int4) via LiteRT-LM | Yes: it runs inside the app's own process | About 529 MB, Wi-Fi only | Phones with enough memory; to be benchmarked | Optional "better summaries" pack |
| Gemini Nano via ML Kit GenAI Summarization | No: returns `BACKGROUND_USE_BLOCKED` unless the app is on screen | None (shipped by AICore) | Pixel 9 and later, Galaxy S25 and later, some others | "Rebuild now" while the app is open |
| User's own Groq API key | Yes | None | All, needs network | Advanced setting for people who want today's server quality |

Notes:

- Gemini Nano also has a per-app daily battery quota (`PER_APP_BATTERY_USE_QUOTA_EXCEEDED`), so it would need the extractive fallback even in the foreground.
- Google has put the MediaPipe LLM Inference API into maintenance-only mode and points new apps to LiteRT-LM, so the Gemma pack should be built on LiteRT-LM from the start.
- Each story is summarized once per build and cached by story ID, as the server does today. A 16-story briefing is 16 short model calls, not one long one.

Sources: [ML Kit GenAI APIs](https://developers.google.com/ml-kit/genai), [LLM Inference guide](https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference), [Gemma 3 on mobile and web](https://developers.googleblog.com/gemma-3-on-mobile-and-web-with-google-ai-edge/).

## Scheduling and reliability

The user sets a "ready by" time instead of a build time. WorkManager starts the build in a window about 90 minutes before it, and the app builds on open if the scheduled run didn't happen. Android doesn't let a news app wake the phone at an exact minute, so the plan works around that rather than against it.

How a morning build runs:

1. After each build, the app queues the next one with WorkManager: a one-time job with an initial delay that lands about 90 minutes before "ready by". Its constraints are a network connection and battery not low.
2. The job is a `CoroutineWorker` that calls `setForeground()`, so it may run past 10 minutes while showing a quiet "Preparing your briefing" notification. On Android 14+ it declares a `dataSync` foreground service type. Android 15 caps `dataSync` at 6 hours a day, far more than one build needs.
3. When the briefing is saved, a local notification says it's ready, as the web app's push does today.
4. Catch-up: if the user opens the app and today's briefing doesn't exist, the app builds it right away in the foreground. This mirrors the server's `catch_up` job and is also when Gemini Nano is allowed.

Constraints this design respects:

- **No exact alarms.** On Android 14, `SCHEDULE_EXACT_ALARM` is denied by default for new installs, and `USE_EXACT_ALARM` is only for alarm-clock and calendar apps. Starting early covers Doze delays instead.
- **Android 16 job quota.** Google warns that long-running workers can use up an app's job quota on Android 16. The fallback is to start the foreground service directly from the worker.
- **Phone makers' battery savers.** Samsung, Xiaomi and others kill background work more aggressively than Pixel. Onboarding links to the battery settings screen (`ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS`) with a one-line explanation, and the app reports the last build time so a missed run is visible.
- **Notification permission.** Android 13+ asks for `POST_NOTIFICATIONS` at runtime, during the welcome step, the same moment the web app asks today.

Sources: [Exact alarms on Android 14](https://developer.android.com/about/versions/14/changes/schedule-exact-alarms), [Long-running workers](https://developer.android.com/develop/background-work/background-tasks/persistent/how-to/long-running), [Android 15 behavior changes](https://developer.android.com/about/versions/15/behavior-changes-15).

## App architecture and sync

One native Kotlin app does all the building and playback. It talks to the same Supabase project as the web app, so a user's sources and settings follow them between web and phone.

Build steps, in order: fetch feeds → read full articles → rank and dedupe → summarize → write script → voice → assemble audio. The three engines behind them: `TextToSpeech`/sherpa-onnx (voice), the extractive port/LiteRT-LM/ML Kit (summaries), MediaCodec (audio).

The build runs top to bottom inside one background job. It reaches outside the phone only for news pages and, once at the start, Supabase.

| Layer | Choice |
| --- | --- |
| Language and UI | Kotlin, Jetpack Compose |
| Background work | WorkManager `CoroutineWorker` with a foreground notification |
| Local data | Room for briefings, chapters and story history; DataStore for settings |
| Network | OkHttp; supabase-kt for auth and the `sources` and `profiles` tables |
| Sign-in | Android Credential Manager "Sign in with Google", handed to Supabase as an ID token |
| Audio | `TextToSpeech` and sherpa-onnx for voices; MediaCodec to encode AAC; Media3 to play |
| Summaries | Extractive port; LiteRT-LM for the Gemma pack; ML Kit GenAI for Gemini Nano |

Sync rules:

- Sources and settings are read from Supabase at the start of each build and cached in Room. A build with no network uses the cached copy and says so in the briefing note.
- Edits made in the app write to Supabase first, the same way the web app does, so row-level security keeps working unchanged.
- A `device_builds` flag on the profile tells the server worker to skip that user, so they never get two briefings and the server never spends time on them.
- Briefings stay on the phone. Uploading them is an open question (see Risks).

## Risks and open questions

The biggest risk is quality, not feasibility: phone summaries and article extraction will start out weaker than the server's Groq and trafilatura pipeline. Each risk below has a check planned before the step that depends on it.

| Risk | Effect | Mitigation | Checked in |
| --- | --- | --- | --- |
| Extractive summaries read worse than Groq's | Briefings sound flatter than the web version | Offer the Gemma pack; compare both on the same day's stories | Phase 2 |
| Readability4J pulls less text than trafilatura | Shorter or empty article bodies, weaker summaries | Run both on 50 real article URLs from the current feeds and compare | Phase 1 |
| Phone makers kill background work | The briefing isn't ready at wake-up | 90-minute head start, catch-up on open, battery-settings prompt, last-build time on screen | Phase 3, on a Samsung and a Pixel |
| Slow builds on older phones | Long builds drain battery; Kokoro or Gemma may not finish | Benchmark a full 16-story build on a low-end phone before shipping each pack | Phases 2 and 4 |
| Python and Kotlin logic drift | Web and Android briefings rank stories differently | Shared JSON fixtures run by both test suites | Phase 1, then every change |
| Google Play foreground-service review | Play asks apps to justify each foreground service type | Declare `dataSync` with a short demo video before the Play listing; not needed while builds ship as a direct APK | Phase 4 |

Open questions:

- **Distribution:** decided. A signed APK is handed out directly through the early phases; the app moves to the Play Store once a final stable version is settled (Phase 4).
- **Sync back:** should phone-built briefings also upload to Supabase so the user can replay them on the web? That restores the archive but costs storage.
- **Shared summaries:** the server already summarizes every built-in story each morning. Should phones download that shared copy when it exists, and summarize locally only for personal sources?
- **Oldest supported Android version:** a higher minimum (such as Android 10) means less compatibility work but excludes older phones.

## Milestones

Each phase ends with something you can install and use, so the plan can stop after any phase and still be worth it.

- **Phase 1: Port the pipeline.** Done when a one-tap build on a phone produces a briefing whose story list matches the Python worker's on the same saved feeds, voiced with the default Android voice. Builds go out as a signed APK that testers install directly.
- **Phase 2: Better summaries.** Done when the Gemma pack downloads, resumes after a dropped connection and summarizes a full briefing on a mid-range phone without being killed.
- **Phase 3: Morning schedule.** Done when a scheduled build finishes before wake time on five mornings in a row on both a Samsung and a Pixel, and the server worker skips that user.
- **Phase 4: Polish and release.** Starts once the APK builds are stable. Done when the Kokoro pack works and a build is in Play internal testing.
