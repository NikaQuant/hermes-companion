## What
<!-- One or two sentences. -->

## Why
<!-- User-facing effect. -->

## How I checked
- [ ] `pytest services/bridge -q`
- [ ] If I touched the PWA: `pytest apps/web/tests -q --browser chromium` against a reloaded bridge
- [ ] No secrets, `.env`, or machine hostnames in the diff
