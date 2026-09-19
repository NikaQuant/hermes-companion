# User guide

## What Hermes Companion is

Hermes Companion is a private browser/PWA interface for the same regular-Hermes profiles and stored sessions used by Hermes Desktop. The bridge keeps Hermes API keys on the server and gives each Companion device a revocable user token.

```text
Browser / PWA / Android wrapper / Windows wrapper
                         │
                         ▼
                Companion bridge
                         │
                         ▼
           regular Hermes profiles only
```

## Sign in

Open the local or private HTTPS address and enter the Companion account email and password. Give the device a meaningful name such as `Nik iPhone` or `Trading VPS Chrome`.

The app stores a short-lived access token and a rotating refresh token in the client. Devices can be revoked individually from **Settings → Devices**.

## Main pages

| Page | Purpose |
|---|---|
| **Command Center** | Bridge status, profile health and shortcuts |
| **Projects** | Fleet view across the allowed profiles |
| **Chat** | Continue a Hermes session or start a durable run |
| **Sessions** | Browse, pin, tag, note, rename, branch or delete sessions |
| **Automations** | View and control Hermes jobs when permitted |
| **Notifications** | Run-completed, failed and approval-related events observed by Companion |
| **Files** | Controlled per-profile upload inbox |
| **Saved Prompts** | Reusable operator prompts stored in Companion only |
| **Live Gateway** | Optional full-fidelity JSON-RPC session surface |
| **Audit** | Administrative event history; administrators only |
| **Administration** | User and profile assignments; administrators only |
| **Settings** | Devices, password, backups and diagnostics |

## Profiles

Use the profile selector at the top of the interface. v0.3 ships with these allowlisted regular profiles:

```text
default           Hermes Core
mentos            Mentos
laneb-lab         Backtest Lab
mql5-forge        MQL5 Engineer
agentic-trading   Agentic Trading
polymarket        Polymarket
```

A profile can be visible but marked unconfigured when its server-side Hermes API key is missing. The client never receives that key.

## Sessions

### Open or continue

1. Select a profile.
2. Open **Sessions** or **Chat**.
3. Select a stored session.
4. Send the next message from **Chat**.

The durable Hermes session ID remains the source of truth. Companion metadata does not alter the Hermes transcript.

### Private metadata

Companion can store:

- **Pinned** state.
- Up to 20 **tags**.
- A private operator **note**.

These values live in the Companion database, not in Hermes memory or `SOUL.md`.

### Branching and deletion

Branching uses the Hermes session-fork route. Deletion removes the upstream Hermes session and should be treated as destructive. Use branching before experimental rewrites.

## Durable runs

The ordinary **Chat** page uses Hermes durable runs. This supports:

- streamed assistant text;
- tool and subagent events;
- reconnect after browser sleep or refresh;
- stop;
- mid-run steer;
- model override;
- approval cards.

The run ID is saved locally while active so the app can reconnect to `/events` rather than starting a duplicate request.

### Approvals

The default remote policy exposes only:

```text
Approve once
Deny
```

Session-wide or permanent approval scopes remain hidden unless the server operator explicitly enables `ALLOW_WIDE_APPROVALS=true`.

Before approving, inspect the command or action shown by Hermes. Companion is a transport and policy layer; it does not make a dangerous operation safe by itself.

## Notifications

Notifications are generated when Companion observes relevant Hermes run events. They are not a guaranteed global copy of every event produced while no Companion client is connected.

Use **Mark all read** after reviewing the inbox. Old notifications are cleaned according to `NOTIFICATION_RETENTION_DAYS`.

## Files

1. Select a profile.
2. Open **Files**.
3. Choose a permitted file.
4. Upload it to the profile-specific inbox.
5. Use its approved server path or reference in an authorized workflow.

Uploads are validated by extension and size, hashed with SHA-256, and optionally passed through a configured scanner. They are not automatically inserted into every Hermes prompt.

See [FILES.md](FILES.md).

## Saved prompts

Saved prompts are operator conveniences. A prompt may be global or associated with one profile. Selecting **Use** copies it into the chat composer; it does not execute automatically.

## Live Gateway

The **Live Gateway** page is optional. It provides a richer session attachment path through `hermes serve`, including gateway events and server-to-client questions.

The bridge obtains a one-time ticket and opens the WebSocket. The upstream session token never enters browser JavaScript. See [LIVE_GATEWAY.md](LIVE_GATEWAY.md).

## Install as a PWA

In a supported browser:

1. Open the private HTTPS Companion URL.
2. Use the browser's **Install app** or **Add to Home Screen** command.
3. Launch Hermes Companion from the installed icon.

A secure HTTPS origin is normally required for installability outside `localhost`.

## Desktop handoff

The optional Hermes Desktop plugin reads the focused regular profile and durable session ID, then opens Companion with those identifiers. Authentication still happens in Companion; the URL contains no Hermes API key.

## Device and password controls

Under **Settings**:

- rename devices by signing in again with a clearer device name;
- revoke a selected device;
- sign out all devices;
- change the account password;
- review bridge diagnostics.

Changing a password revokes existing sessions and requires a new sign-in.

## Troubleshooting

| Symptom | Check |
|---|---|
| Profile says unconfigured | Matching `HERMES_API_KEY_*` is missing from `.env` or Hermes |
| Profile offline | Hermes gateway/API listener is not running or key does not match |
| Stream stops after phone sleep | Reopen Chat; the client should reconnect to the stored run ID |
| Live Gateway unavailable | `HERMES_SERVE_URL` or session token is absent; enable the optional task |
| File rejected | Extension, size, scanner result or per-profile permission |
| Login repeatedly fails | Check credentials, device time and rate-limit window |
| PWA does not install | Use HTTPS or localhost and verify manifest/service worker reachability |

For operator recovery, use [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md).
