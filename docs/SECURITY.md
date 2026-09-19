# Security model

## Security objectives

Hermes Companion is designed to let authenticated humans use selected regular-Hermes profiles remotely without placing Hermes credentials in a browser, APK or Desktop plugin.

The model is **defence in depth**, not an assertion that natural-language remote control is risk-free.

## Enforced controls

### Explicit profile allowlist

Only entries in `config/profiles.json` are routable. Each route prefix must be either empty for `default` or exactly `/p/{slug}` for a named profile.

The following identities and normalized aliases are blocked:

- Live Safe
- Live Judge
- HermesSafety / Hermes Safety
- Safety World

These checks apply during configuration loading, user-profile assignment, request routing and Desktop plugin installation.

### Distinct upstream secrets

Each allowed profile uses a distinct `HERMES_API_KEY_*` environment variable. Client-visible profile data exposes only whether a key is configured; it never exposes the key or its environment-variable name.

`HERMES_SERVE_SESSION_TOKEN` is likewise server-only. A live browser receives a one-time ticket with a short TTL, not the upstream token.

### Companion authentication

- Password hashing: `scrypt` with a random salt.
- Access tokens: random opaque values, short lifetime, SHA-256 hashes stored in SQLite.
- Refresh tokens: random opaque values, rotating and hashed at rest.
- Devices: stable client-generated device IDs; each device can be revoked independently.
- Password change/reset: revokes existing device sessions.
- Login throttle: bounded attempts per IP/email window.
- Administrator protection: last-admin deletion/demotion and unsafe self-demotion are refused.

### Per-user profile access

Administrators may access every configured regular profile. Ordinary users receive an explicit subset. A non-assigned profile is returned as unavailable rather than leaking its existence through operation errors.

### Per-operation profile policy

Each profile declares independent permissions:

```text
read
chat
session_write
run_control
approval
jobs_write
files_write
gateway_live
```

A user assignment does not override a disabled profile operation.

### Approval scope

Remote approvals default to:

```text
once
deny
```

`session` and `always` are rejected unless `ALLOW_WIDE_APPROVALS=true` is deliberately configured. Wide approval is not recommended for a general remote client with terminal-capable tools.

### Live Gateway policy

The WebSocket relay:

- consumes one-time, expiring tickets;
- locks every method to the ticket profile;
- permits only a reviewed JSON-RPC method allowlist;
- rejects administrative slash-command prefixes;
- permits attachment paths only when they correspond to a staged Companion upload owned by the user/profile;
- permits responses only to server-request IDs actually observed on that connection;
- enforces maximum frame size and upstream connection timeout.

The live relay is optional. Disabling it does not affect durable HTTP runs.

### Controlled file inbox

Uploads are written below a server-selected user/profile directory. Clients cannot select an arbitrary destination. The bridge validates:

- authenticated user and assigned profile;
- `files_write` permission;
- filename normalization;
- allowed extension;
- maximum byte size;
- SHA-256;
- optional external scanner result.

A live gateway path attachment is accepted only if the exact resolved path exists in that user/profile upload record.

### Browser and HTTP controls

The bridge sets:

- Content Security Policy for self-hosted assets and the Companion WebSocket;
- `frame-ancestors 'none'`;
- no-referrer policy;
- MIME-sniffing protection;
- restrictive Permissions Policy;
- private/no-store caching on sensitive downloads;
- API request-size enforcement;
- no service-worker caching of `/api/` responses.

A reverse proxy should enforce a body-size limit as an earlier boundary.

### Audit

The audit log covers authentication, user/profile administration, run starts and controls, approvals, session/job mutations, file lifecycle, backups and live-gateway connections.

It does not intentionally record:

- plaintext passwords;
- raw access/refresh tokens;
- Hermes API keys;
- the live-gateway token;
- full user prompts.

## Backup sensitivity

A normal Companion backup excludes `.env`, Hermes API keys and raw device tokens. It still contains account email addresses, password hashes, audit records, saved prompts and private session metadata. Treat it as confidential.

A `-IncludeSecrets` disaster backup includes `.env` in plaintext inside the ZIP. It must be protected by filesystem ACLs and additional encrypted storage.

## Required deployment posture

- Keep Hermes API `8642` on loopback.
- Keep optional `hermes serve` `9119` on loopback.
- Keep Companion on loopback when using a tunnel/reverse proxy.
- Expose only Companion `8787` through private HTTPS or a VPN.
- Add an identity-aware proxy layer when practical.
- Protect `.env`, SQLite, uploads, logs and backups with Windows ACLs.
- Do not install or configure this project under `HermesSafety`.

## Trading boundary

Hermes Companion is not a substitute for the Safety EA, Sentinel, terminal lock, origin guard or typed order validation.

Any future live-order UI should use a narrow schema containing explicit account, symbol, direction, order type, size, risk, stop and expiry fields, with independent safety enforcement. A natural-language prompt alone is not sufficient authorization.
