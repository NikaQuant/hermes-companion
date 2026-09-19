# Hermes Companion v0.3.0 — build and validation report

Generated: **2026-09-17 UTC**

## Build environment

| Tool / target | State |
|---|---|
| Python | 3.13.5 |
| Node.js | 22.16.0 |
| Java | 21 |
| Browser automation | Python Playwright + system Chromium |
| Android SDK / Gradle platform | Not installed |
| Rust/Cargo | Not installed |
| Windows native build host | Not available |
| PowerShell runtime | Not available; scripts received static review only |
| Private signing credentials | Intentionally unavailable |

## Final validation results

| Check | Result | Evidence |
|---|---:|---|
| Backend test suite | **PASS** | 28/28 tests |
| Python compilation | **PASS** | Bridge application and operator scripts |
| Deterministic PWA build | **PASS** | 8 files; one hashed JS and one hashed CSS bundle |
| Release validator | **PASS** | v0.3.0 metadata, 19 required docs, exactly six allowed profiles |
| Production JavaScript syntax | **PASS** | Canonical source and hashed output bundle |
| Desktop-plugin JavaScript syntax | **PASS** | `node --check` |
| Desktop browser workflow | **PASS** | Fleet, projects, sessions, pinning, run stream, notifications, prompts, files, administration, settings and audit |
| Mobile browser workflow | **PASS** | 390px command center and shared-session chat |
| Browser console/page errors | **PASS** | None in the tested workflow |
| Live gateway relay fixture | **PASS** | Gateway ready, RPC relay, policy and ticket-replay rejection |
| Backup/restore | **PASS** | Format 2, SHA-256/size validation, SQLite quick check, token scrubbing, upload restore |
| Real-host smoke utility | **PASS against fixture** | 14 HTTP checks including temporary session/run/transcript/delete/logout |
| Safety World boundary | **PASS** | Hard-blocked aliases plus exact six-profile release allowlist |
| Clean source-tree validation | **PASS** | No `.env`, runtime DB, virtualenv, node_modules, cache or signing key included |

## Automated test coverage

The 28-test backend suite covers:

- login, refresh rotation, logout and password/session revocation;
- stable device binding and independent device revocation;
- administrator user creation, profile assignment and self-protection;
- regular-profile authorization and hard Safety World rejection;
- durable run creation, SSE passthrough, stop, steer and approval policy;
- notifications derived from observed run events;
- saved prompts and private session metadata;
- controlled upload policy and profile isolation;
- project/diagnostics/backup endpoints;
- live-gateway ticket use, replay rejection and RPC policy;
- raw-attachment, slash-prefix and arbitrary-workdir restrictions;
- scanner-command parsing on Windows-style paths;
- restore traversal protection and release-packager secret exclusions.

## Browser evidence

| Screenshot | Dimensions | Surface |
|---|---:|---|
| `artifacts/e2e/command-center.png` | 1440 × 1000 | Six-profile fleet and bridge health |
| `artifacts/e2e/projects.png` | 1440 × 1189 | Project overview |
| `artifacts/e2e/sessions.png` | 1440 × 1000 | Session browser and pin state |
| `artifacts/e2e/chat-run.png` | 1440 × 1000 | Completed durable streamed run |
| `artifacts/e2e/notifications.png` | 1440 × 1000 | Notification inbox |
| `artifacts/e2e/files.png` | 1440 × 1000 | Controlled file inbox |
| `artifacts/e2e/administration.png` | 1440 × 1261 | Accounts, diagnostics and backups |
| `artifacts/e2e/settings.png` | 1440 × 1407 | Devices and client settings |
| `artifacts/e2e/audit.png` | 1440 × 1000 | Audit trail |
| `artifacts/e2e/mobile-command-center.png` | 390 × 2391 | Full mobile fleet view |
| `artifacts/e2e/mobile-chat.png` | 390 × 902 | Mobile shared-session chat |

## Architecture delivered

```text
PWA / Capacitor source / Tauri source / Desktop handoff plugin
                              │
                              ▼
              Hermes Companion Bridge :8787
       auth · devices · profile ACL · audit · files
       notifications · backups · SSE · one-use WS tickets
                   │                       │
                   ▼                       ▼
          Hermes API :8642       optional hermes serve :9119
          durable HTTP/SSE        live JSON-RPC/WebSocket
                   └───────────┬───────────┘
                               ▼
      default · mentos · laneb-lab · mql5-forge
            agentic-trading · polymarket
```

## Not compiled or target-validated here

| Item | Reason / exact next step |
|---|---|
| Signed Android APK/AAB | Install Android SDK, run `scripts/build-android.ps1`, sign with operator keystore |
| Windows MSI/NSIS/EXE | Use Windows + Rust/Cargo, run `scripts/build-windows-app.ps1`, sign with operator certificate |
| Hermes Desktop plugin runtime | Install on the regular Hermes Desktop and run the handoff checklist |
| Actual six-profile Hermes integration | Run `scripts/real-hermes-smoke.py` on Nik's regular Hermes VPS |
| Production HTTPS/access policy | Configure the chosen domain, VPN/tunnel and identity provider |
| Background push delivery | Add an external push provider and device credentials |
| Live MT5/project data cards | Bind adapters to the actual VPS schemas/processes |

## Assessment

The v0.3 bridge and PWA are complete, runnable and tested as a private control-plane release. Native wrappers are build-ready source, not claimed binaries. The remaining high-value work is deployment and target-runtime verification against Nik's real regular-Hermes environment.
