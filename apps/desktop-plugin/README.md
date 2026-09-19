# Hermes Desktop handoff plugin

This is a deliberately thin regular-Hermes plugin. It reads the focused Desktop profile/session IDs and opens the authenticated Companion interface. It does not contain Hermes API keys, proxy tools, or load Safety World profiles.

Install:

```powershell
.\scripts\install-desktop-plugin.ps1 -Force
```

Default destination:

```text
%LOCALAPPDATA%\hermes\desktop-plugins\hermes-companion\plugin.js
```

The installer refuses the `HermesSafety` account and Safety World-like paths.

Desktop plugin loading changes across Hermes releases, so source and JavaScript syntax validation are not a substitute for testing the user's installed Desktop build. The PWA and bridge remain independent of the optional plugin.

See `docs/DESKTOP_PLUGIN.md` for the full acceptance procedure.
