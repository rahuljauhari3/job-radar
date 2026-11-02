# Job Radar iOS app

SwiftUI, iOS 17+, SwiftData. Reads `feed.json` from the poller and keeps your application tracker on the device.

- **Feed:** new matches grouped by the day they were first seen, with tier/score badges, filters (tier, co-ops, hide tracked, hide citizenship/sponsorship flags) and search. Swipe right = Applied, swipe left = Save / Hide.
- **Detail:** why it matched, flags, description snippet, every source it was seen on, the status picker, and "Copy /tailor-resume prompt".
- **Tracker:** Saved → Applied → OA → Interview → Offer / Rejected, with OA and interview rates.
- **Settings:** ntfy topic and one-tap subscribe, backup local notifications per tier, feed URL.
- Deep links: `jobradar://job/<id>` (the "Open in Job Radar" button on each ntfy push) and `jobradar://feed`.

## Build

```bash
brew install xcodegen
cd ios && xcodegen generate && open JobRadar.xcodeproj
```

## Run on your iPhone (free Apple ID)

1. In Xcode: Settings → Accounts → add your Apple ID.
2. Select the JobRadar target → Signing & Capabilities → Team: your personal team. If the bundle ID is taken, change `com.rahuljauhari.JobRadar` to something unique.
3. Plug in the iPhone, pick it as the run destination, press Run. On the phone: Settings → General → VPN & Device Management → trust your developer certificate.
4. If Xcode says Developer Mode is required: on the phone, Settings → Privacy & Security → Developer Mode → on, then restart.
5. Free signing expires after 7 days; press Run again to renew.

Or from the terminal, with the phone plugged in (your team ID is the `OU=` value printed by `security find-certificate -c "Apple Development" -p | openssl x509 -noout -subject`):

```bash
xcodebuild -project JobRadar.xcodeproj -scheme JobRadar -destination 'platform=iOS,name=<your iPhone name>' -derivedDataPath build/device -allowProvisioningUpdates DEVELOPMENT_TEAM=<team id> build
xcrun devicectl device install app --device '<your iPhone name>' build/device/Build/Products/Debug-iphoneos/JobRadar.app
```

## Tests

```bash
xcodebuild -project JobRadar.xcodeproj -scheme JobRadar -destination 'platform=iOS Simulator,name=iPhone 18 Pro' test
```

The UI tests read the feed from `http://127.0.0.1:8765/feed.json`, so first serve one: `python3 -m http.server 8765 --bind 127.0.0.1 --directory ../data` after a local `python -m radar run`. Set `TEST_RUNNER_JOBRADAR_DEEPLINK_ID` to a job id in that feed to run the deep-link test, and `TEST_RUNNER_JOBRADAR_SHOTS_DIR` to save screenshots.
