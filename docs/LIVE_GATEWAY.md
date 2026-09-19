# Optional live gateway

## Purpose

The normal Companion chat path uses the official Hermes HTTP API and durable `/v1/runs`. The optional live path relays the Hermes TUI gateway JSON-RPC/WebSocket protocol exposed by `hermes serve`.

Use it when you need features that are naturally gateway-scoped:

- attach to a live session;
- server-to-client approval or clarification requests;
- slash-command resolution and dispatch;
- live session status and event replay;
- compression and richer session controls;
- subagent steer/interrupt.

Durable HTTP runs remain the safer default for ordinary phone use.

## Topology

```text
Browser
  │ one-use Companion ticket
  ▼
/api/gateway/ws
  │ X-Hermes-Session-Token (server side only)
  ▼
hermes serve --host 127.0.0.1 --port 9119
  │
  ▼
TUI gateway JSON-RPC session
```

The browser never receives `HERMES_SERVE_SESSION_TOKEN`.

## Enable on Windows

```powershell
.\scripts\enable-live-gateway.ps1
```

This operation:

1. Generates a random upstream session token.
2. Writes it to the protected Companion `.env`.
3. registers **Hermes Companion Live Gateway** in Task Scheduler;
4. starts `hermes serve` on loopback;
5. restarts the Companion bridge so it reads the configuration.

Disable it with:

```powershell
.\scripts\disable-live-gateway.ps1
```

## Ticket flow

1. Authenticated client requests `POST /api/gateway/{profile}/ticket`.
2. The bridge verifies user assignment and `gateway_live` permission.
3. The bridge creates a short-lived, single-use random ticket.
4. Client connects to `/api/gateway/ws?ticket=...`.
5. Ticket is atomically consumed and cannot be replayed.
6. Bridge connects upstream using its server-side session token.

Ticket TTL is controlled by `GATEWAY_TICKET_SECONDS` and is capped at five minutes.

## Method policy

Only reviewed methods in `GATEWAY_ALLOWED_METHODS` are accepted. The default includes session lifecycle, prompt submission, model options, command dispatch, compression, event replay, subagent controls and controlled attachment methods.

The relay additionally:

- stamps/locks the selected profile;
- rejects profile changes in client parameters;
- blocks administrative slash-command prefixes;
- restricts file attachment paths to approved upload directories;
- tracks legitimate server-request IDs before forwarding responses;
- caps frame size;
- audits ticket creation and connection lifecycle.

This is not a generic transparent WebSocket proxy.

## Server requests

Hermes may send JSON-RPC requests such as:

```text
approval
clarify
sudo
secret
vault.code
vault.unlock_prompt
connection
```

The current Companion UI renders supported approval and clarification-style cards. Unsupported methods are answered with JSON-RPC `-32601` so Hermes fails fast rather than waiting indefinitely.

Never enter a high-value reusable secret into a remote UI unless that workflow has been explicitly reviewed.

## Restrictions

- Keep `hermes serve` on `127.0.0.1`.
- Do not reverse-proxy port 9119.
- Do not reuse the upstream session token as a user password.
- Do not enable live gateway access for Safety World profiles.
- Treat `command.dispatch` as privileged; the bridge rejects obvious administrative prefixes but cannot prove every natural-language command harmless.

## Validation

Protocol-fixture integration test:

```bash
python scripts/gateway-e2e.py
```

Real host validation is described in [REAL_HERMES_VALIDATION.md](REAL_HERMES_VALIDATION.md).
