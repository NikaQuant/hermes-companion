# Delivery status — Hermes Companion v0.3.0

## Built and verified in this environment

| Component | Delivery state |
|---|---|
| FastAPI Companion bridge | Built; 28/28 automated backend tests pass |
| Production web/PWA | Built with hashed assets, manifest and service worker |
| Desktop browser workflow | Passed against protocol fixtures |
| 390px mobile workflow | Passed against protocol fixtures |
| Durable Hermes HTTP/SSE path | Implemented and fixture-tested |
| Guarded live WebSocket path | Implemented; one-use-ticket relay fixture passed |
| Multi-user/device administration | Implemented and tested |
| Notifications, prompts, metadata, files | Implemented and browser-tested |
| Backup/restore | Format-2 redacted backup and restore validation passed |
| Diagnostics bundle | Implemented; secret-exclusion validation included |
| Real-host smoke utility | Implemented and passed all 14 checks against the HTTP fixture |
| Desktop plugin source | Complete and JavaScript syntax-validated |
| Android and Windows wrappers | Source and CI/build workflows included |

## Requires the regular Hermes VPS/Desktop/phone

- Match the six generated API keys to the six regular Hermes profiles.
- Run `scripts/real-hermes-smoke.py` against the actual gateway and provider/tool configuration.
- Load and exercise the Desktop plugin in the installed Hermes Desktop version.
- Compile/sign Android and Windows binaries using operator-owned signing credentials.
- Configure private HTTPS/VPN access and verify phone sleep/reconnect behavior.
- Connect project-specific dashboards to live Mentos, backtest, MQL5, Agentic Trading and Polymarket data schemas.

## Deliberately excluded

- Safety World, Live Safe, Live Judge and HermesSafety.
- Hermes API keys or `hermes serve` tokens in browser, PWA, APK, Tauri or Desktop-plugin code.
- Fabricated signing keys or claims of signed native binaries.
- Direct exposure of Hermes ports 8642 or 9119.

## First installation command

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap-windows.ps1
```

For a stable install location with rollback copies:

```powershell
.\scripts\deploy-windows.ps1 -InstallRoot C:\HermesCompanion
```
