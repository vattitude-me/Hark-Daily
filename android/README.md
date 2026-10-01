# Morning Brief for Android

A standalone Android app that builds the briefing **on the phone**: it fetches the feeds, ranks them, writes the
summaries (with Groq if you add a key, otherwise a built-in summarizer), records them with the phone's own
text-to-speech voices, and plays the result. No server worker is needed. Signing in with the web app's account is optional;
it syncs your settings and sources.

- Android 10+. Download the APK from the [releases](https://github.com/vattitude-me/morning-brief-voice/releases) tagged `android-v*`.
- Builds every morning before your "ready by" time, and again if a scheduled build was missed.
- For the best voices, install **Speech Recognition & Synthesis from Google** and download an English voice pack.

## Build

```bash
cd android
./gradlew testDebugUnitTest assembleDebug     # needs JDK 21 and the Android SDK
```

Release builds are signed from `keystore.properties` (gitignored) or the `ANDROID_KEYSTORE*` environment variables.
Pushing a tag like `android-v0.2.0` makes CI build a signed APK and attach it to a GitHub release.
