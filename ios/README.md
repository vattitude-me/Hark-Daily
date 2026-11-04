# Hark Daily — iOS Native Shell

Hark Daily's iOS application uses a **Native Hybrid Shell** architecture powered by [Capacitor](https://capacitorjs.com/) and Apple iOS system frameworks (`AVFoundation`, `WebKit`, `UserNotifications`).

## Architecture & Native Features

1. **Uninterrupted Background Audio Playback**:
   - `AVAudioSession` initialized with `.playback` category and `.spokenAudio` mode in `AppDelegate.swift`.
   - `UIBackgroundModes` configured with `audio`, `fetch`, and `remote-notification` in `Info.plist`.
   - Full integration with Apple Lock Screen controls, Dynamic Island / Now Playing scrubber, Control Center, and CarPlay/Bluetooth transports via standard `navigator.mediaSession`.
2. **Deep Links & Universal Schemes**:
   - Custom URL Scheme: `me.vattitude.morningbrief://`
   - Associated Domains for universal links: `hark.vattitude.ca`
   - Native OAuth flow callbacks and story deep links (`/story/:slug`).
3. **Over-The-Air Parity & Local Fallback**:
   - Points directly to `https://hark.vattitude.ca` with local offline web asset bundling as fallback.
   - Synchronized via `npx cap sync ios`.
4. **Hardware Safe Area & Status Bar Integration**:
   - Native dark theme `#0d0d0d` background.
   - Automatic viewport cover with safe area insets.

## Building Locally

### Prerequisites
- macOS with Xcode 15+ (Xcode 16 / 17 recommended)
- Node.js 20+

### Syncing Web Assets & Plugins
```bash
npm run sync
# or
npx cap sync ios
```

### Opening in Xcode
```bash
npx cap open ios
```

### Building via Command Line (xcodebuild)
```bash
# Build for iOS Simulator (iPhone 16)
xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -destination 'platform=iOS Simulator,name=iPhone 16' build

# Build for Generic iOS Device (Release Archive)
xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release -destination 'generic/platform=iOS' archive -archivePath build/HarkDaily.xcarchive
```
