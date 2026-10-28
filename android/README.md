# Hark Daily for Android

Native Android client built with Jetpack Compose, Material3 tokens, and Media3 background playback. Plays daily editions streamed from Supabase Storage with optional on-device offline synthesis.

| Today | Following along | Sources | Settings |
| :---: | :---: | :---: | :---: |
| ![](../docs/screenshots/android-today-light.png) | ![](../docs/screenshots/android-playing-dark.png) | ![](../docs/screenshots/android-sources-light.png) | ![](../docs/screenshots/android-settings-light.png) |

- **Listening Modes**: Supports **Podcast** (default two-host conversation) and **Full Brief**.
- **Follow-Along Visor**: Highlights the active story in real time with synchronized playback and inline read-along transcripts.
- **Background Audio**: Android Media3 notification and lock-screen playback controls with scrubber.
- **Pull-to-Refresh**: Native pull gesture on TodayScreen to check for updated editions.
- **Offline Fallback**: Optional on-device Kokoro TTS offline engine via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx).
- **Custom Lineup**: Reorder categories and toggle story counts per section.

Requires Android 10+ (API 29+). Download signed APKs from [GitHub Releases](https://github.com/vattitude-me/Hark-Daily/releases). Store assets are in [`docs/play-store`](../docs/play-store).

## Build

```bash
cd android
./gradlew testDebugUnitTest assembleDebug     # needs JDK 21 and the Android SDK
```

Release builds are signed from `keystore.properties` (gitignored) or the `ANDROID_KEYSTORE*` environment variables.
Google sign-in returns to `<applicationId>://auth`, so add `me.vattitude.morningbrief://auth` (and the `.debug` one)
to Supabase → Authentication → URL Configuration → Redirect URLs.
Pushing a tag like `android-v0.2.0` makes CI build a signed APK and attach it to a GitHub release.
