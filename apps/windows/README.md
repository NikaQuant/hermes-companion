# Windows Tauri wrapper

This optional wrapper packages the same built PWA as a Windows application. Hermes Desktop plus the Desktop handoff plugin remains the native Hermes-first experience; Tauri is useful when a separate branded Companion window is preferred.

## Build

Requirements: Node.js, Rust/Cargo, Tauri Windows prerequisites and WebView2.

```powershell
.\scripts\build-windows-app.ps1
```

Configured outputs:

```text
apps\windows\src-tauri\target\release\bundle\msi\
apps\windows\src-tauri\target\release\bundle\nsis\
```

The wrapper contains no Hermes API keys. Configure the local or private HTTPS Companion bridge address in the app. Production trust requires the operator's own Windows code-signing certificate.
