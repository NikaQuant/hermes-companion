# Contributing to Hermes Companion

Thanks for wanting to help. This project is a local security bridge + phone PWA in front of [Hermes Agent](https://hermes-agent.nousresearch.com). Keep that boundary sharp.

## Ground rules

1. **No secrets in git.** `.env`, `services/bridge/data`, `backups`, `logs`, and `config/profiles.json` (generated per machine) stay out.
2. **Don't weaken the allowlist.** Safety World / Live Safe / Live Judge names stay blocked.
3. **Don't talk to Hermes except on loopback.** The browser talks only to the Companion bridge.
4. **User-facing copy goes through `LABELS` in `apps/web/standalone/app.js`.** No `window.prompt` / `confirm` — they break iOS home-screen PWAs. Use `sheet()` / `ask()` / `okay()`.
5. **Tests before "it works".** Backend: `pytest services/bridge`. UI: `pytest apps/web/tests --browser chromium` against a running bridge.

## Setup

```powershell
git clone https://github.com/NikaQuant/hermes-companion.git
cd hermes-companion
python -m venv .venv
.\.venv\Scripts\pip install -e .\services\bridge[dev]
copy config\profiles.example.json config\profiles.json
.\.venv\Scripts\python.exe scripts\build-web.py
.\.venv\Scripts\python.exe -m pytest services\bridge -q
```

## Making a change

1. Branch from `main`.
2. Small, one-purpose commits. Conventional style is welcome (`fix:`, `feat:`, `docs:`).
3. If you touch the PWA, run `scripts\reload-bridge.ps1` so tests hit the new bundle — `Stop-ScheduledTask` alone leaves the old process alive.
4. Open a pull request. CI must be green.

## Where code lives

| Path | What |
|---|---|
| `apps/web/standalone/` | The PWA (`app.js` + `app.css`) |
| `services/bridge/` | FastAPI bridge |
| `scripts/` | Install, wire, backup, release |
| `docs/` | Human and AI operator guides |

## Reporting bugs

Use GitHub Issues. Include: OS, Companion version (the `v0.3.x · hash` under the Hermes logo), and `logs/bridge.log` with secrets redacted.

Security issues: see [`SECURITY.md`](SECURITY.md) — don't file a public issue.
