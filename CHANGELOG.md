# Changelog

## 0.3.2 — 2026-09-19

- Visible version + build stamp (`v0.3.2 · <hash>`) in the phone header, login page and About, so you can tell which build is on screen.
- All ~120 hard-coded dark colours replaced with semantic tokens; light theme now fully themed (surfaces, borders, text, status colours).
- More menu and conversation menu are tappable row lists instead of a dropdown.

## 0.3.1 — 2026-09-19

Phone-first UX overhaul of the Companion PWA.

- Plain-language labels (Home, Chat, Conversations, Alerts) instead of infrastructure jargon.
- Bottom tab bar on phones (Home · Chat · Conversations · Alerts · More) plus a More sheet.
- In-app `<dialog>` sheets replace every `window.prompt()` / `confirm()` (those are broken in iOS home-screen PWAs).
- Readable type (15px body / 14px small) and 44px touch targets on phones.
- Home shows “Needs your attention”, assistants, recent conversations, and a first-run checklist (home screen / alerts / passkey).
- Conversations as cards with a per-conversation menu; session IDs and profile slugs hidden from the main UI.
- Chat: Enter sends, Shift+Enter newline, autosizing composer, jump-to-latest.
- Settings regrouped: Sign-in · Alerts · This app · Advanced. Light theme + system default.
- Offline banner, focus rings, reduced-motion, longer error toasts, “new version ready” toast.
- `/api/overview` now includes `attention.unread` and `attention.approvals`.
- Playwright phone/desktop UI suite against the live bridge.

## 0.3.0 — 2026-09-17

### Control plane

- Added multi-user Companion accounts with administrator-managed profile assignments.
- Added independently revocable devices, rotating refresh tokens, password reset and logout-all controls.
- Added project overview, notification inbox, saved prompts and private session pins/tags/notes.
- Added a controlled file inbox with extension/size validation, SHA-256 recording, retention and optional scanner integration.
- Added diagnostics, audit filtering and redacted/downloadable Companion backups.

### Hermes integration

- Added an optional guarded `hermes serve` JSON-RPC/WebSocket relay for live sessions, clarification/approval requests, slash commands, compression, event replay and subagent controls.
- Added short-lived single-use gateway tickets; the browser never receives the upstream Hermes session token.
- Added method allowlisting, selected-profile locking, frame-size limits, server-request correlation and attachment-path restrictions.
- Blocked raw/base64 attachment methods, arbitrary `cwd` injection and obvious administrative slash-command prefixes from remote live-gateway clients.
- Added a real-host smoke tool for read-only checks and an optional temporary session/model-call test.

### Security and recovery

- Split profile permissions into read, chat, session-write, run-control, approval, jobs-write, files-write and live-gateway capabilities.
- Preserved the hard Safety World exclusion at configuration, administration, routing and Desktop-plugin installation boundaries.
- Fixed refresh rotation so a token remains bound to its original device and cannot evade device revocation.
- Made one-use handoff and gateway-ticket consumption atomic.
- Added format-2 backups with file sizes/SHA-256 values, SQLite integrity validation, traversal-safe restore and token scrubbing.
- Added local redacted diagnostics bundles and production operations scripts for deployment, upgrade, rollback and uninstall.

### Client and deployment

- Expanded the PWA with Projects, Notifications, Files, Saved Prompts, Live Gateway and Administration surfaces.
- Added mobile navigation and responsive layouts for the expanded control plane.
- Added stable Windows deployment, upgrade/rollback and optional loopback-only live-gateway tasks.
- Added Android/Capacitor and Windows/Tauri CI build workflows.
- Added a thin Hermes Desktop handoff plugin with no embedded Companion or Hermes credentials.

### Validation

- Expanded automated backend coverage from 14 to 28 tests.
- Added self-contained HTTP and `hermes serve` protocol fixtures.
- Added desktop/mobile browser workflows covering login, fleet, sessions, streamed runs, notifications, prompts, files, diagnostics, backups, devices and audit.
- Added backup/restore, diagnostics-bundle and real-smoke-tool fixture validation.
- Fixed test collection so running `pytest` no longer creates a database inside the source tree.

## 0.2.0 — 2026-09-17

- Replaced the unavailable npm-dependent production path with a deterministic, dependency-free PWA build.
- Implemented command-center, sessions, chat, durable run, tool timeline, approval, automation, audit and settings screens.
- Fixed double-consumption of upstream HTTPX SSE streams.
- Added stream time limits, proxy trust controls, body-size checks and stronger HTTP security headers.
- Added rotating refresh recovery, Desktop handoff, Android/Tauri source and 14 backend tests.

## 0.1.0

- Initial architecture and source scaffold.
