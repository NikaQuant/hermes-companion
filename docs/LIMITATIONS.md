# Limitations and pending target-runtime work

## Not completed in this build environment

| Item | Reason / next action |
|---|---|
| Signed Android APK/AAB | Android SDK, Gradle and operator signing keystore are absent |
| Signed Windows MSI/EXE | Rust/Cargo, Windows build host and signing certificate are absent |
| Real Hermes profile validation | User's VPS, keys, models and tools are not reachable from this container |
| Installed Desktop plugin validation | Requires the user's exact Hermes Desktop build |
| Real background push notifications | Requires a push provider, application credentials and device registration |
| Production reverse-proxy deployment | Requires the user's domain/VPN/tunnel account |
| MT5/project-specific data adapters | Requires actual project schemas, files and processes on the VPS |

## Functional constraints

- Notifications reflect events observed through Companion; they are not a guaranteed global Hermes event ledger.
- The in-memory login limiter is per bridge process and resets after restart.
- PWA offline support covers the application shell, not Hermes conversations or runs.
- File extension validation is not a substitute for malware scanning.
- Live gateway command filtering cannot semantically prove that every accepted prompt or slash command is harmless.
- Companion session notes/tags are local to Companion and do not synchronize into Hermes memory.
- `PUBLIC_APP_URL` does not configure DNS, TLS or access policy by itself.
- The Desktop plugin opens an external authenticated URL; it does not silently transfer a Companion login.
- A gateway restart can interrupt an in-flight durable or live session depending on Hermes ownership state.

## Architecture decision

The shipped PWA remains the primary client because it is the only target compiled and exercised end-to-end in this container. Android and Windows wrappers intentionally share that UI rather than implementing divergent clients.

## Safety constraint

Safety World is intentionally unsupported. Adding its profiles is not a missing feature; it is a hard isolation boundary.
