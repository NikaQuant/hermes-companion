# Architecture

## System boundary

Hermes Companion is another client of the regular Hermes Agent runtime. It does not scrape, remote-control or inject into the visible Hermes Desktop window.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Client surfaces                                                     │
│ browser · installed PWA · Capacitor Android · Tauri Windows        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                                │ opaque Companion access token
┌───────────────────────────────▼─────────────────────────────────────┐
│ Hermes Companion Bridge                                              │
│ FastAPI :8787                                                        │
│                                                                      │
│ auth/device sessions     profile/user ACL      audit                 │
│ durable SSE proxy        notifications         saved prompts         │
│ session metadata         controlled uploads    backups/diagnostics   │
│ one-time WS tickets      method filtering      static PWA hosting    │
└──────────────────────┬────────────────────────┬──────────────────────┘
                       │ loopback               │ loopback
                       │ per-profile API key    │ fixed server token
           ┌───────────▼──────────┐  ┌─────────▼─────────────────────┐
           │ Hermes API :8642     │  │ optional hermes serve :9119   │
           │ HTTP + SSE           │  │ JSON-RPC over WebSocket       │
           │ durable runs         │  │ live sessions + questions     │
           └───────────┬──────────┘  └─────────┬─────────────────────┘
                       └──────────────┬─────────┘
                                      ▼
                     regular Hermes profile homes
        default · mentos · laneb-lab · mql5-forge
               agentic-trading · polymarket

Hermes Desktop plugin ─ focused profile + durable session ─► Companion URL
```

## Why the bridge exists

A browser bundle, PWA and APK are inspectable. Embedding an `API_SERVER_KEY` or the `hermes serve` session token in a client would expose the entire corresponding Hermes tool surface. The bridge therefore:

1. authenticates a Companion user and device;
2. verifies that the user may access the requested profile;
3. verifies the operation-specific permission;
4. attaches the appropriate upstream secret only on a loopback request;
5. records the control-plane action without recording passwords or API keys.

## Two Hermes transports

### Durable HTTP/SSE

Used by the normal **Chat** page and all automation-oriented controls.

```text
POST /v1/runs                  create durable run
GET  /v1/runs/{id}             poll status
GET  /v1/runs/{id}/events      attach/re-attach SSE
POST /v1/runs/{id}/approval    answer a pending approval
POST /v1/runs/{id}/steer       course-correct at a tool boundary
POST /v1/runs/{id}/stop        interrupt the run
```

This transport is suitable for mobile sleep/reconnect because the run exists independently of the browser stream.

### Optional live JSON-RPC/WebSocket

Used by **Live Gateway**. It connects through `hermes serve` and provides live-session functions that are not equivalent to one durable HTTP request: clarification cards, server-to-client requests, slash-command dispatch, live session resume/activation and detailed event flow.

The browser never connects directly to `hermes serve`. It requests a one-time Companion ticket, then the bridge opens the upstream WebSocket with the server-side token.

## Durable run lifecycle

1. Client selects a stored Hermes session.
2. Client posts input to `/api/profiles/{profile}/runs` with an idempotency key.
3. Bridge forwards to profile-owned Hermes `/v1/runs` with a stable user/profile session key.
4. Browser subscribes to the Companion SSE endpoint.
5. The bridge observes—but does not rewrite—tool, subagent, approval and terminal events.
6. Relevant events create deduplicated Companion notifications.
7. Browser stores the active run ID per profile/session and can reconnect after reload.
8. On terminal status, the client reloads the authoritative transcript from Hermes.

## Identity and storage

The stable `X-Hermes-Session-Key` is derived from:

```text
HMAC-SHA256(APP_SECRET, companion-user-id + profile-slug)
```

It is stable for one Companion user/profile pair and cannot be used to recover the user password or app secret.

| Data | Source of truth |
|---|---|
| Stored sessions and transcript | Hermes profile database |
| Agent memory | Hermes profile |
| Skills, MCP, tools and model configuration | Hermes profile |
| Hermes scheduled jobs | Hermes profile |
| Companion users and device sessions | Companion SQLite |
| Profile assignments and operation policy | Companion SQLite + `config/profiles.json` |
| Notifications, saved prompts, pins/tags/notes | Companion SQLite |
| Uploaded file bytes | Controlled Companion upload root |
| Hermes API keys and live-gateway token | `.env` on bridge host |
| Client refresh token | Local storage on that client |
| Client access token | Session storage |

Companion does not copy Hermes memory or maintain a competing transcript database.

## Profile multiplexing

The default Hermes gateway owns the API listener. Named profiles are routed through the official multiplexed prefixes:

```text
/                    default
/p/mentos            mentos
/p/laneb-lab         laneb-lab
/p/mql5-forge        mql5-forge
/p/agentic-trading   agentic-trading
/p/polymarket        polymarket
```

Every named profile receives its own API key. The bridge profile allowlist maps one slug to one exact route prefix and refuses alternate path construction.

## Canonical frontend

`apps/web/standalone/` is the canonical PWA source. `scripts/build-web.py` creates a deterministic, hashed, dependency-free production bundle in `apps/web/dist/`.

`apps/web/src/` is retained as an optional React/Vite prototype track. It is not the production source of truth for v0.3 and should not be used to judge feature parity.
