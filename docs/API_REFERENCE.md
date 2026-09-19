# Companion bridge API reference

Base URL: `http://127.0.0.1:8787` locally, or the configured private HTTPS URL remotely.

Except for health, login, refresh and the PWA assets, routes require:

```http
Authorization: Bearer <companion-access-token>
```

This token is a Companion token, not a Hermes API key.

## Authentication

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Authenticate and register/bind a device |
| POST | `/api/auth/refresh` | Rotate refresh and access tokens |
| POST | `/api/auth/logout` | Revoke current access and optional refresh token |
| POST | `/api/auth/logout-all` | Revoke all user tokens |
| GET | `/api/auth/me` | Current user/device |
| GET | `/api/auth/devices` | List active devices |
| DELETE | `/api/auth/devices/{device_id}` | Revoke one device |
| POST | `/api/auth/password` | Change own password and revoke sessions |

## Profiles and projects

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/profiles` | Visible profile policy and status flags |
| GET | `/api/profiles/{profile}/health` | Selected upstream Hermes health |
| GET | `/api/overview` | Bridge/profile overview and unread count |
| GET | `/api/projects` | Fleet summary: health, recent sessions, jobs, capabilities |

## Sessions

All session routes are under `/api/profiles/{profile}/sessions`.

| Method | Suffix | Permission |
|---|---|---|
| GET | `` | `read` |
| POST | `` | `session_write` |
| GET | `/{session_id}/messages` | `read` |
| PATCH | `/{session_id}` | `session_write` |
| DELETE | `/{session_id}` | `session_write` |
| POST | `/{session_id}/fork` | `session_write` |

Query and body shapes are proxied to the corresponding official Hermes native session routes after profile authorization and ID encoding.

## Companion session metadata

Base: `/api/profiles/{profile}/session-meta`.

| Method | Route | Purpose |
|---|---|---|
| GET | `` | List metadata for the profile |
| GET | `/{session_id}` | Read one metadata record |
| PUT | `/{session_id}` | Replace pinned/tags/note |

## Durable runs

Base: `/api/profiles/{profile}/runs`.

| Method | Route | Purpose |
|---|---|---|
| POST | `` | Start a Hermes durable run |
| GET | `/{run_id}` | Poll status |
| GET | `/{run_id}/events` | SSE lifecycle stream |
| POST | `/{run_id}/approval` | Resolve approval |
| POST | `/{run_id}/steer` | Queue guidance at a tool boundary |
| POST | `/{run_id}/stop` | Interrupt the run |

`POST /runs` accepts `input`, optional `session_id`, model/instruction fields and an optional idempotency key. The bridge creates a key when absent and forwards it to Hermes.

## Jobs

Base: `/api/profiles/{profile}/jobs`.

| Method | Route | Purpose |
|---|---|---|
| GET | `` | List jobs |
| POST | `` | Create job (`jobs_write`) |
| GET | `/{job_id}` | Get job |
| PATCH | `/{job_id}` | Update job (`jobs_write`) |
| DELETE | `/{job_id}` | Delete job (`jobs_write`) |
| POST | `/{job_id}/{action}` | `run`, `pause` or `resume` (`jobs_write`) |

## Models and capabilities

| Method | Route |
|---|---|
| GET | `/api/profiles/{profile}/model-options` |
| GET | `/api/profiles/{profile}/capabilities` |

## Notifications

| Method | Route |
|---|---|
| GET | `/api/notifications` |
| PATCH | `/api/notifications/{id}` |
| POST | `/api/notifications/read-all` |
| DELETE | `/api/notifications/{id}` |

## Saved prompts

| Method | Route |
|---|---|
| GET | `/api/prompts` |
| POST | `/api/prompts` |
| PUT | `/api/prompts/{id}` |
| DELETE | `/api/prompts/{id}` |

## Files

| Method | Route |
|---|---|
| GET | `/api/files?profile=<slug>` |
| POST | `/api/files` multipart upload |
| GET | `/api/files/{id}/download` |
| DELETE | `/api/files/{id}` |

Upload and delete require profile `files_write` permission.

## Live gateway

| Method | Route |
|---|---|
| POST | `/api/gateway/{profile}/ticket` |
| WebSocket | `/api/gateway/ws?ticket=<one-use-ticket>` |

## Administration

| Method | Route |
|---|---|
| GET | `/api/admin/users` |
| POST | `/api/admin/users` |
| PATCH | `/api/admin/users/{id}` |
| POST | `/api/admin/users/{id}/password` |
| DELETE | `/api/admin/users/{id}` |
| GET | `/api/audit` |
| GET | `/api/diagnostics` |
| POST | `/api/diagnostics/profiles/{profile}/probe` |
| GET/POST | `/api/backups` |
| GET/DELETE | `/api/backups/{name}` |

## Handoff

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/handoff` | Create an authenticated one-time handoff token |
| GET | `/api/handoff/{token}` | Consume token and return profile/session |

Direct `?profile=...&session=...` links also work after normal Companion authentication and contain no secret.

## Health

```text
GET /api/health
```

Returns bridge version and status without disclosing profile API keys.
