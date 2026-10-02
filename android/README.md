# Morning Brief for Android

A standalone Android app that builds the briefing **on the phone**: it fetches the feeds, ranks them, writes the
summaries (with Groq if you add a key, otherwise a built-in summarizer), records them in a natural Kokoro voice or the
phone's own text-to-speech, and plays the result. No server worker is needed. Signing in with Google (the same account as the web app) is
optional; it syncs your settings and sources.

- Android 10+. Download the APK from the [releases](https://github.com/vattitude-me/morning-brief-voice/releases) tagged `android-v*`.
- Builds every morning before your "ready by" time, and again if a scheduled build was missed.
- **Natural voices:** Settings → Voice → Natural downloads the full-quality Kokoro model (about 350 MB, once) and runs
  it offline with [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). It's the same seven voices as the web app.
  Otherwise the phone's own voice reads the briefing.

## Build

```bash
cd android
./gradlew testDebugUnitTest assembleDebug     # needs JDK 21 and the Android SDK
```

Release builds are signed from `keystore.properties` (gitignored) or the `ANDROID_KEYSTORE*` environment variables.
Google sign-in returns to `<applicationId>://auth`, so add `me.vattitude.morningbrief://auth` (and the `.debug` one)
to Supabase → Authentication → URL Configuration → Redirect URLs.
Pushing a tag like `android-v0.2.0` makes CI build a signed APK and attach it to a GitHub release.
