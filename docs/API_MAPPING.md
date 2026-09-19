# Companion-to-Hermes API mapping

The bridge authorizes the Companion user and profile, adds the server-held profile key, and forwards to the official Hermes surface.

## HTTP API mapping

| Companion route | Hermes upstream route |
|---|---|
| `GET /api/profiles/{p}/health` | `GET /health/detailed`, fallback `/health` |
| `GET /api/profiles/{p}/sessions` | `GET /api/sessions` |
| `POST /api/profiles/{p}/sessions` | `POST /api/sessions` |
| `GET /api/profiles/{p}/sessions/{id}/messages` | `GET /api/sessions/{id}/messages` |
| `PATCH /api/profiles/{p}/sessions/{id}` | `PATCH /api/sessions/{id}` |
| `DELETE /api/profiles/{p}/sessions/{id}` | `DELETE /api/sessions/{id}` |
| `POST /api/profiles/{p}/sessions/{id}/fork` | `POST /api/sessions/{id}/fork` |
| `POST /api/profiles/{p}/runs` | `POST /v1/runs` |
| `GET /api/profiles/{p}/runs/{id}` | `GET /v1/runs/{id}` |
| `GET /api/profiles/{p}/runs/{id}/events` | `GET /v1/runs/{id}/events` |
| `POST .../approval` | `POST /v1/runs/{id}/approval` |
| `POST .../steer` | `POST /v1/runs/{id}/steer` |
| `POST .../stop` | `POST /v1/runs/{id}/stop` |
| `GET /api/profiles/{p}/model-options` | `GET /api/model/options` |
| `GET /api/profiles/{p}/capabilities` | `GET /v1/capabilities` |
| Companion jobs routes | Corresponding `/api/jobs` routes |

For named profiles, the Hermes client prepends `/p/<profile>` to the upstream path and uses that profile's distinct bearer key.

The bridge also sends a stable per-user/per-profile `X-Hermes-Session-Key` where supported, while explicit stored `session_id` remains authoritative for resuming a durable conversation.

## WebSocket mapping

Companion's `/api/gateway/ws` relays to:

```text
<hermes-serve-url>/api/ws
```

using `X-Hermes-Session-Token` server-side. The JSON-RPC wire format is preserved after policy checks.

Supported method families include:

```text
session.*
prompt.submit / prompt.background
command.resolve / command.dispatch
model.options
delegation.status
subagent.interrupt / subagent.steer
spawn_tree.*
controlled attachment methods
```

## Companion-owned data

These are not proxied to Hermes:

- users, devices and tokens;
- profile assignments;
- session pins/tags/notes;
- notifications;
- saved prompts;
- upload records;
- audit events;
- backup manifests;
- one-time handoff and gateway tickets.

## Upstream errors

The bridge translates Hermes HTTP errors into bounded client errors. It does not disclose the upstream bearer key. SSE content is relayed event-by-event with disconnect handling and configured time limits.
