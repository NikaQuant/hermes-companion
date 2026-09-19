# Hermes Companion — Installation Guide for AI Operators

**Audience:** an AI agent (Hermes Agent, Claude, ChatGPT, etc.) installing Hermes Companion on
behalf of a human on **their own** Windows machine. Every step below has the exact command,
the expected result, and what to do when it differs. Follow the order. Do not skip verification.

**Human-facing summary:** `../INSTALL.md`. Phone setup: `PHONE_ACCESS.md`.

---

## 0. What you are installing

Hermes Companion = a small local web service ("bridge", FastAPI, port **8787**, loopback only)
+ a phone-first web app (PWA) it serves. The bridge talks to the human's existing **Hermes Agent**
HTTP API on `127.0.0.1:8642`. Users log into the Companion with an email/password created during
install; the Companion holds per-profile Hermes API keys server-side. The browser never sees Hermes keys.

Ports: `8787` Companion (the only one that may be reverse-proxied) · `8642` Hermes API (loopback only)
· `9119` optional `hermes serve` live gateway (loopback only). **Never expose 8642 or 9119.**

This package is generic: it contains **no** accounts, keys, hostnames or profiles from anyone else.
Profiles are discovered from the local `hermes profile list` at install time.

---

## 1. Preconditions (verify, do not assume)

Run each in a normal PowerShell (Administrator not yet required):

| Check | Command | Expected | If not |
|---|---|---|---|
| Python ≥ 3.11 | `python --version` | `Python 3.11.x` or newer | Install from python.org, tick "Add to PATH", reopen the terminal |
| Hermes CLI | `hermes --version` | prints a version | Install Hermes Agent first; reopen terminal so PATH updates |
| Hermes has profiles | `hermes profile list` | a table with at least `default` | Hermes is not set up; finish Hermes onboarding first |
| Hermes API reachable (optional now) | `hermes gateway status` | anything, no crash | fine if not running yet — wiring step starts it |
| Port free | `netstat -ano \| findstr :8787` | no `LISTENING` line | another Companion/app is on 8787; stop it or pass `-Port` later |
| Not Safety World | `whoami` | not `HermesSafety`; install path does not contain `Hermes-Safety` | choose another user/path (installer refuses otherwise) |

Choose a permanent folder, e.g. `C:\HermesCompanion`. Unzip so that `C:\HermesCompanion\install.cmd` exists
(no extra nested folder).

---

## 2. Install

### 2a. One-click (preferred)

Double-click `install.cmd`, or from **Administrator** PowerShell:

```powershell
cd C:\HermesCompanion
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-windows.ps1
```

The script, in order:

1. Refuses Safety World users/paths. Checks `python` and `hermes`.
2. **Discovers profiles** → writes `config\profiles.json` (`scripts\discover-profiles.py --force`).
   Expected output: `Wrote ...config\profiles.json` followed by one line per profile, `default` first.
3. **Creates `.env`** and the first admin user (`scripts\generate-env.py`). It prompts:
   `Initial administrator email:` then `Initial administrator password (16+ recommended):` (hidden, min 12 chars).
   Expected: `Initial administrator created.` and `The plaintext password was never written to .env.`
   ⚠ If you are driving this non-interactively, run `generate-env.py --email <email>` and let the human type the password;
   never pass `--password` on a command line the human can see in history.
4. Tightens ACLs on `.env`, `services\bridge\data`, `backups`, `logs` (current user + SYSTEM only).
5. Creates `.venv`, `pip install -e .\services\bridge`, builds the PWA (`build-web.py` → `Built Hermes Companion web <ver>: 8 files`),
   runs `validate-release.py --installed` → `Release validation passed for Hermes Companion <ver>`.
6. **Wires Hermes** (`configure-hermes.ps1` → `wire-hermes.py`): for each profile in `profiles.json`, writes
   `API_SERVER_KEY` into that profile's own `.env` (found via `hermes profile show <slug>` → `Path:`), plus
   `API_SERVER_ENABLED=true` on `default` only; sets `hermes -p default config set gateway.multiplex_profiles true`;
   installs/restarts the default gateway. Expected last lines: `Wired default, <others>`.
7. Installs the Desktop handoff plugin (harmless if Hermes Desktop is absent).
8. Registers Task Scheduler entry **`Hermes Companion Bridge`** (at logon, current user) and starts it.
9. Polls `http://127.0.0.1:8787/api/health` until `status: ok`.

Success line: `Hermes Companion is ready at http://127.0.0.1:8787`.

### 2b. Flags

```
-SkipHermesConfiguration   don't touch Hermes (.env of profiles / gateway) — Companion will show profiles as "not connected"
-SkipStartupTask           don't register the Windows task (run manually: .\scripts\Start-HermesCompanion.ps1)
-SkipDesktopPlugin         skip the Hermes Desktop plugin
-EnableLiveGateway         also start a loopback `hermes serve` on 9119 for real-time sessions (optional)
-AdminEmail <email>        pre-fill the admin email
```

Re-running `bootstrap-windows.ps1` is safe: it preserves an existing `.env`, `profiles.json` (if it lists >1 profile) and database.

---

## 3. Verify (mandatory)

```powershell
cd C:\HermesCompanion
Invoke-RestMethod http://127.0.0.1:8787/api/health
```
Expected: `status ok`, `service hermes-companion-bridge`, `version <x.y.z>`.

```powershell
Get-ScheduledTask 'Hermes Companion Bridge' | Select State
netstat -ano | findstr :8787
```
Expected: `Running` and one `LISTENING` line on `127.0.0.1:8787` with a PID.

Real end-to-end check against the human's Hermes (read-only, prompts for the Companion login):

```powershell
.\.venv\Scripts\python.exe .\scripts\real-hermes-smoke.py --url http://127.0.0.1:8787 --profile default
```
Expected: a JSON report with `"ok": true` and each probe `200`. If the human doesn't want to type the
password into the terminal, skip this and verify in the browser instead: open `http://127.0.0.1:8787`,
sign in, Home should list the profiles with **Ready** badges.

Automated regression (optional, takes ~1 min, uses a throwaway admin it deletes afterwards):

```powershell
.\.venv\Scripts\python.exe -m pip install "playwright>=1.47,<2" "pytest-playwright>=0.5,<1"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest apps\web\tests -q --browser chromium
```
Expected: all passed. Backend unit tests: `cd services\bridge; ..\..\.venv\Scripts\python.exe -m pytest -q`.

---

## 4. Phone access

Follow `PHONE_ACCESS.md`. For an agent, the essential commands are:

```powershell
tailscale serve --bg 8787                      # prints https://<host>.<tailnet>.ts.net ; may first require enabling Serve via a printed link
.\scripts\set-public-url.ps1 -Url https://<host>.<tailnet>.ts.net
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\reload-bridge.ps1   # rebuild + real restart
```

`PUBLIC_APP_URL` enables passkeys (WebAuthn RP ID is derived from its host) and is auto-added to CORS.
`TRUST_PROXY_HEADERS=true` in `.env` is correct when Tailscale Serve (a loopback proxy) fronts the bridge — it
makes the audit log show real phone IPs. Set it with a text editor, then reload.

---

## 5. Day-2 operations

| Task | Command |
|---|---|
| Restart after changing `.env` or code | `.\scripts\reload-bridge.ps1` (kills the listener PID, rebuilds, restarts task, checks health) |
| Logs | `logs\bridge.log` |
| Backup (token-scrubbed) | `.\scripts\backup-local.ps1 -Label before-change` |
| Restore | stop the bridge, `.\scripts\restore-backup.ps1 -Archive <zip>` |
| Add/remove a profile later | `.\.venv\Scripts\python.exe scripts\discover-profiles.py --force` → add missing `HERMES_API_KEY_<NAME>=<random>` lines to `.env` → `scripts\wire-hermes.py` → reload |
| Reset admin password | `.\scripts\reset-admin-password.ps1` |
| Diagnostics bundle (redacted) | `.\scripts\collect-diagnostics.ps1` |
| Uninstall | `.\scripts\uninstall-windows.ps1` then delete the folder |

---

## 6. Failure table (real cases)

| Symptom | Cause | Fix |
|---|---|---|
| `The 'hermes' command is not on PATH` | terminal opened before Hermes install, or Hermes not installed | reopen terminal; `hermes --version` must work first |
| `Profile discovery failed` / only `default` found | `hermes profile list` output format not parsed | run `python scripts\discover-profiles.py --print` and inspect; hand-write `config\profiles.json` using `config\profiles.example.json` |
| Task shows `Ready`, log has only a header line, nothing on 8787 | launcher output redirection under Task Scheduler | already fixed (uses `logs\start-bridge.cmd`); check `logs\bridge.log` for a Python traceback |
| Config change "didn't apply" after Stop/Start task | `Stop-ScheduledTask` leaves the python child alive | use `scripts\reload-bridge.ps1` (kills by port PID) |
| `validate-release.py` fails on `.env`/db/backups | ran without `--installed` on an installed tree | always `--installed` after install |
| Browser: **Failed to fetch** on login | phone not on the VPN, wrong URL, or a stale `Server URL` saved | Tailscale Connected; use exact `https://…ts.net`; Advanced → Server URL blank |
| Passkey "Add" does nothing / error | no `PUBLIC_APP_URL` (passkeys need a real HTTPS host) or browser lacks WebAuthn | set-public-url + reload; use Safari/Chrome on the phone |
| Profile shows **Not connected** | its `HERMES_API_KEY_<NAME>` missing/empty in `.env` or not written to the profile `.env` | `wire-hermes.py --dry-run` shows the plan; check the profile's `.env` has `API_SERVER_KEY` |
| `hermes -p default gateway install` "preflight" or "another gateway running" | a gateway is already running for another profile | `hermes gateway status`; only the **default** profile's gateway may listen; stop others' `API_SERVER_ENABLED` |
| `email-validator` 422 on login/create | reserved domain (`.local`, `.test`, `example.com`) | use a real-looking email domain |
| `MpCmdRun` rejects every upload (if a scanner is configured) | Defender needs `-File <path>`; the bridge appends the path | `UPLOAD_SCAN_COMMAND` must END with `-File` |
| WebSocket live gateway 403 | `hermes serve` authenticates with `?token=` query param | already handled in `routes/gateway.py`; ensure `HERMES_SERVE_SESSION_TOKEN` matches |

---

## 7. What NOT to do

- Do not run as the `HermesSafety` account or under a `Hermes-Safety` path — refused by design.
- Do not put a password on a command line or in chat. `generate-env.py` prompts with hidden input.
- Do not expose 8642/9119. Only 8787, and only via a private tunnel (Tailscale) or an authenticated reverse proxy.
- Do not hand-edit `config.yaml` of Hermes; the wiring script only touches each profile's `.env` (with `.env.bak-*` backups) and uses `hermes config set`.
- Do not ship `.env`, `services\bridge\data`, `backups`, `logs` to anyone — they contain this user's keys and login database.

---

## 8. File map

```
install.cmd                      one-click launcher (elevates, runs bootstrap)
INSTALL.md                       human quick start
docs/AGENT_INSTALL_GUIDE.md      this file
docs/PHONE_ACCESS.md             Tailscale + PWA on phone
scripts/bootstrap-windows.ps1    full guided install
scripts/discover-profiles.py     hermes profile list → config/profiles.json
scripts/generate-env.py          .env + first admin (keys per profile)
scripts/wire-hermes.py           per-profile .env wiring + multiplex gateway
scripts/reload-bridge.ps1        rebuild PWA + real restart + health check
scripts/set-public-url.ps1       set PUBLIC_APP_URL (phone HTTPS address)
scripts/enable-live-gateway.ps1  optional hermes serve on 9119
scripts/backup-local.ps1 / restore-backup.ps1 / uninstall-windows.ps1
config/profiles.json             generated at install (default only in the shipped zip)
config/profiles.example.json     reference shape
services/bridge/                 FastAPI bridge (+ tests)
apps/web/standalone/             the PWA source; apps/web/dist is the built copy
apps/web/tests/                  Playwright UI tests (phone viewport)
```
