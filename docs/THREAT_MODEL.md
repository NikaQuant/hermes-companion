# Threat model

## Scope

This threat model covers the Companion bridge, PWA, optional wrappers, Desktop handoff plugin, local database, uploads and the optional `hermes serve` relay. It does not model the internal security of model providers, Windows, Cloudflare, Tailscale, MetaTrader, brokers or Safety World.

## Assets

- Hermes profile API keys.
- Optional `hermes serve` session token.
- Companion app secret.
- User password hashes and device tokens.
- Hermes session IDs and transcript access.
- Uploaded files.
- Approval authority and run/job controls.
- Audit records and backups.

## Trust boundaries

```text
untrusted remote client
        │ HTTPS
        ▼
reverse proxy / VPN / identity gate
        │
        ▼
Companion authentication + authorization
        │ loopback secrets
        ├────────► Hermes API :8642
        └────────► hermes serve :9119 (optional)
```

The local Windows account and anyone with read access to `.env` or the database are trusted host administrators.

## Primary threats and controls

| Threat | Control |
|---|---|
| Hermes API key extraction from APK/browser | Keys exist only in bridge `.env`; never serialized to clients |
| Token theft | Short access TTL, rotating refresh tokens, per-device binding and revocation |
| Brute-force login | Generic errors and bounded in-memory rate limit |
| Cross-profile access | Explicit user assignment plus endpoint-level profile authorization |
| Safety World crossover | Hard-blocked normalized identities, six-profile allowlist and installer account/path checks |
| CSRF | Bearer-token API; no ambient cookie authentication |
| XSS token theft | Strict CSP, escaped dynamic HTML, no third-party runtime script dependency |
| Arbitrary filesystem access | Managed upload roots, random names and path containment checks |
| Malicious upload | size/extension allowlist, optional scanner, no automatic execution |
| WebSocket privilege escalation | one-use ticket, profile lock, method allowlist, slash-command blocks and server-request ID tracking |
| Approval widening | `once`/`deny` default; wider scopes require explicit server setting |
| Duplicate paid/side-effecting run | Hermes idempotency key on durable run admission |
| Backup bearer replay | routine backup deletes active token/handoff/ticket rows |
| Secret leakage in diagnostics | no `.env` values or database rows; text redaction; review before sharing |
| Direct Hermes internet exposure | deployment keeps 8642 and 9119 loopback-only |

## Residual risks

- A fully compromised bridge host can read Hermes keys and impersonate Companion.
- A malicious or vulnerable reverse proxy can observe bearer tokens unless end-to-end controls are used.
- Natural-language model/tool execution cannot be made equivalent to a typed trading authorization protocol.
- Extension allowlisting does not prove file content is safe.
- The live gateway method allowlist reduces surface but does not prove every accepted command is harmless.
- Browser local storage is accessible to script running in that origin; CSP and dependency minimization reduce but do not eliminate XSS risk.
- In-memory login throttling resets on process restart and is not a distributed rate limiter.

## Trading boundary

Companion must not become the sole authority for live trading. Existing independent controls—Sentinel, Safety EA, terminal lock, origin restrictions, account/risk governors and explicit typed execution APIs—remain authoritative.

The shipped project dashboards are observability/control-plane views, not a bypass around those controls.

## Hardening recommendations

1. Use a private VPN or identity-aware HTTPS tunnel.
2. Restrict the reverse proxy to expected users/devices.
3. Run the bridge as the regular non-Safety Windows identity with least privilege.
4. Protect `.env`, database, uploads and backups with Windows ACLs.
5. Keep `ALLOW_WIDE_APPROVALS=false`.
6. Configure a malware scanner.
7. Rotate keys after suspected host exposure.
8. Review audit events and revoke stale devices.
9. Test restore procedures.
10. Keep Safety World physically and logically separate.
