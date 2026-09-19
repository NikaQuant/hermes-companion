# Native builds

The release ships a built PWA plus source/build workflows for Android and Windows. This build environment does not contain the Android SDK, Gradle, Rust/Cargo or signing credentials, so no signed native binary is claimed.

## Android with Capacitor

### Requirements

- Node.js 20+
- npm 10+
- JDK 17 or 21
- Android Studio / Android SDK
- configured `ANDROID_HOME`
- Android signing keystore for release builds

### Build debug source/project

```powershell
.\scripts\build-android.ps1
```

The script installs dependencies, builds the canonical PWA, creates/synchronizes the Capacitor Android project and invokes the available Gradle build.

Expected debug APK location after a successful native build:

```text
apps\web\android\app\build\outputs\apk\debug\app-debug.apk
```

### Runtime address

A wrapper cannot reach `127.0.0.1:8787` on the Windows VPS unless it runs there. Configure the app/UI to use the private HTTPS Companion URL. Do not embed Hermes API keys in Capacitor configuration.

### Release signing

Use a private keystore and Android's normal signing configuration. Do not commit the keystore, password or generated signed APK if the repository is public.

## Windows with Tauri

### Requirements

- Node.js/npm
- Rust stable toolchain and Cargo
- Tauri prerequisites for Windows
- Microsoft WebView2
- code-signing certificate for trusted distribution

Build:

```powershell
.\scripts\build-windows-app.ps1
```

Tauri targets MSI and NSIS installers. The wrapper loads the compiled PWA and connects to the configured bridge URL.

## PWA as the primary deliverable

The PWA is the most portable and most-tested client in v0.3. It supports install-to-home-screen without maintaining separate UI code for each platform.

## CI workflows

The repository includes GitHub Actions workflows for validation and native builds. Native artifacts produced by CI are unsigned/debug unless repository secrets and signing steps are configured by the operator.

## What was validated in the build container

| Item | Result |
|---|---|
| Canonical PWA build | Passed |
| Desktop/mobile browser workflow | Passed |
| JavaScript syntax | Passed |
| Capacitor configuration source | Included and inspected |
| Tauri configuration source | Included and inspected |
| APK/AAB compile | Not available in this container |
| MSI/NSIS compile | Not available in this container |
| Production signing | Requires operator credentials |
