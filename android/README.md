# Hark Daily — Android Smart Native Shell

Hark Daily's Android application uses a **Smart Native Shell** architecture powered by [Capacitor](https://capacitorjs.com/) and native Android system services.

## Why Hybrid Smart Shell?

1. **Instant Updates & Over-The-Air Parity**: Points directly to `https://hark.vattitude.ca` with local offline web asset bundling as a seamless fallback. Web UI updates, new edition rollouts, and design improvements are reflected instantly on user devices without requiring store approvals or new binary installs.
2. **Native Media Session & Unbroken Background Playback**:
   - `HarkMediaService` runs as an Android Foreground Service with type `mediaPlayback`.
   - CPU `PARTIAL_WAKE_LOCK` prevents OS battery-saver suspension and thread freezing when the screen turns off or when the user switches to other apps.
   - Synchronizes with standard `navigator.mediaSession` for system lockscreen controls, notification transport actions, and Bluetooth metadata.
3. **Hardware Keep-Screen-On**:
   - `FLAG_KEEP_SCREEN_ON` is dynamically enabled whenever audio is actively playing, preventing the phone display from sleeping while reading along with the briefing teleprompter.
   - Automatically releases when audio is paused or completed to preserve battery life.
4. **Branded Native Notifications**:
   - High-priority Android notification channel (`hark_daily_briefing`) with app branding and custom icon (`ic_notification`), avoiding generic browser notification banners that users typically dismiss.

## Architecture

- **Application ID**: `me.vattitude.morningbrief`
- **Main Activity**: `me.vattitude.morningbrief.MainActivity`
- **Playback Service**: `me.vattitude.morningbrief.HarkMediaService`
- **Bridge Interface**: `window.HarkNative` exposed directly into WebView:
  - `setKeepScreenOn(boolean keepOn)`
  - `notifyPlaybackState(boolean isPlaying, String title, String artist)`
  - `postNotification(String title, String body)`
  - `isNativeShell()`

## Building Locally

### Prerequisites
- JDK 21
- Android SDK (API 35/36)

### Running Unit Tests
```bash
./gradlew testDebugUnitTest
```

### Assembling Release APK
```bash
./gradlew assembleRelease -PversionName=1.0.0 -PversionCode=10000
```
Output: `app/build/outputs/apk/release/morning-brief-1.0.0.apk`

### Assembling Release App Bundle (Google Play)
```bash
./gradlew bundleRelease -PversionName=1.0.0 -PversionCode=10000
```
Output: `app/build/outputs/bundle/release/morning-brief-release.aab`
