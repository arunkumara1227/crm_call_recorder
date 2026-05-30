# CRM Call Recorder — Android Companion App

Watches the phone's built-in call-recordings folder and uploads new files to the
[crm_call_recorder/](../) Odoo module. Per PDF §2, the app does **not** record
calls itself — it relies on the phone's built-in recorder.

## Build phases

| Phase | Status | Scope |
|---|---|---|
| 2A | ✅ Built | Project scaffold, Settings screen, `/ping` test |
| 2B | ⏳ Next | FileObserver service + CallLog lookup + Room queue |
| 2C | ⏳ | UploadWorker + retry + WorkScheduler |
| 2D | ⏳ | Status UI + DetailScreen + polish |

## Requirements

- Android Studio Koala (2024.1.x) or newer
- JDK 17 (bundled with Android Studio)
- Android SDK 34 installed (`SDK Manager → Android 14 — UpsideDownCake`)

## Open in Android Studio

1. Android Studio → File → Open → select [c:\odoo19\custom_addons\crm_call_recorder\android](.).
2. Wait for Gradle sync. On first sync it'll download AGP 8.6.0 + dependencies (~200 MB).
3. If sync fails on KSP: Android Studio → File → Invalidate Caches → Restart.

## Build the APK from CLI

```powershell
cd c:\odoo19\custom_addons\crm_call_recorder\android
.\gradlew assembleDebug
```

The debug APK lands at `app\build\outputs\apk\debug\app-debug.apk`.

## Install on the Infinix phone

1. Enable **Developer Options** on the phone: Settings → About → tap "Build number" 7 times.
2. Enable **USB Debugging** in Developer Options.
3. Plug phone into PC via USB. Accept the RSA fingerprint prompt.
4. From this folder:

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

5. Open the **CRM Call Recorder** app on the phone (debug suffix: `.debug`).

## Configure (Phase 2A goal)

1. Open the app → **Settings** tab.
2. Enter:
   - **Server URL**: `http://<your-PC-IP>:8069` (find with `ipconfig` on PC; phone must be on same Wi-Fi).
   - **Database**: `test9`.
   - **API Key**: `my-secret-key-2026` (or whatever you rotated to).
3. Tap **Save**.
4. Tap **Test Connection** → expect green `✓ Connected · server_time=…`.

If 401: bad API key. If 404: wrong DB name. If timeout: PC firewall blocking 8069 — open Windows Firewall → allow Odoo on Private networks.

## Project structure

```
android/
├── app/src/main/
│   ├── AndroidManifest.xml            # Phase 2A: INTERNET only. 2B adds storage/calllog.
│   ├── res/                           # strings, theme, backup rules
│   └── kotlin/com/alphalize/crmcallrec/
│       ├── CrmCallRecApp.kt           # Application: builds ServiceLocator
│       ├── ServiceLocator.kt          # Manual DI — no Hilt
│       ├── MainActivity.kt            # Bottom-nav: Status | Settings
│       ├── data/
│       │   ├── prefs/SecurePrefs.kt   # EncryptedSharedPreferences wrapper
│       │   └── net/                   # Retrofit + Moshi + ApiKeyInterceptor
│       └── ui/
│           ├── status/                # Phase 2A: placeholder; 2D: real list
│           ├── settings/              # URL/DB/key + Test Connection
│           └── theme/                 # Material 3 dynamic color
├── gradle/
│   ├── libs.versions.toml             # Version catalog
│   └── wrapper/                       # Gradle 9.0.0 (copied from skeleton)
└── build.gradle.kts / settings.gradle.kts / app/build.gradle.kts
```

## Tech stack

- **Kotlin** 2.0.20, **Compose** BOM 2024.09.02, **Material 3**
- **Retrofit** 2.11 + **OkHttp** 4.12 + **Moshi** 1.15
- **Room** 2.6.1 (via **KSP** — no kapt)
- **WorkManager** 2.9.1
- **EncryptedSharedPreferences** (security-crypto 1.1.0-alpha06)
- **minSdk 26** (Android 8.0), **targetSdk 34** (Android 14)
- **No Hilt** — manual DI via `ServiceLocator` keeps builds fast and the surface small

## What works after Phase 2A

| Feature | Status |
|---|---|
| App installs and launches | ✓ |
| Bottom nav switches Status / Settings | ✓ |
| Settings persist across restarts (encrypted) | ✓ |
| Test Connection hits `/crm_call_recorder/ping` and reports success/error | ✓ |
| Wrong API key shows `401 — bad or missing API key` | ✓ |
| Wrong DB shows `404 — wrong database or URL` | ✓ |
| **File watcher** | Phase 2B |
| **Auto upload** | Phase 2C |
| **Recent uploads list** | Phase 2D |
