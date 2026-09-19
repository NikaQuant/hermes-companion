# Hermes Desktop handoff plugin

## Purpose

The plugin is deliberately thin. It reads the focused regular-Hermes profile and stored session ID from Desktop state and opens Hermes Companion.

It does not:

- store a Hermes API key;
- talk directly to port 8642;
- execute trades;
- load Safety World profiles;
- replace the main Desktop chat surface.

## Installation

```powershell
.\scripts\install-desktop-plugin.ps1 -Force
```

Default destination:

```text
%LOCALAPPDATA%\hermes\desktop-plugins\hermes-companion\plugin.js
```

The installer refuses the `HermesSafety` account and Safety World-like paths.

## Contributions

The plugin registers:

- `/hermes-companion` page;
- **Companion** sidebar entry;
- status-bar button;
- command-palette actions;
- persisted Companion bridge URL.

The page shows the focused profile and durable session ID and can open or copy a handoff URL.

## Configure the address

Use the plugin page to save either:

```text
http://127.0.0.1:8787
```

or the private HTTPS URL used by remote devices.

The plugin stores only this URL in Desktop plugin storage.

## Handoff semantics

The generated URL carries `profile` and `session` query parameters. These are identifiers, not credentials. Companion still requires a valid login and verifies that the user is assigned to the requested profile.

## Compatibility

Hermes Desktop's plugin SDK and disk-plugin loader evolve. Source and JavaScript syntax are validated in this release, but the exact installed Desktop build must be tested. If the plugin does not load, the PWA remains fully usable and Desktop can be connected through copied session IDs until compatibility is resolved.

See [REAL_HERMES_VALIDATION.md](REAL_HERMES_VALIDATION.md) for acceptance steps.
