# Validate against the real Hermes installation

The packaged tests use protocol-compatible fixtures. This document covers the final target-host verification that cannot be performed inside the build container.

## Preconditions

- Run from the regular Hermes Windows account.
- Hermes gateway is running.
- Companion is healthy at `http://127.0.0.1:8787`.
- Six profile keys in Companion `.env` match their regular Hermes profiles.
- Safety World is not mounted or referenced by Companion.

## Read-only smoke test

```powershell
.\.venv\Scripts\python.exe .\scripts\real-hermes-smoke.py `
  --url http://127.0.0.1:8787 `
  --profile default
```

The script prompts for a Companion login unless credentials are provided through its supported arguments/environment. It verifies:

- bridge health;
- authentication;
- visible profile policy;
- authenticated profile inventory;
- fleet and project overview;
- selected-profile sessions endpoint;
- provider-aware model options;
- selected-profile jobs endpoint.

## Optional write test

```powershell
.\.venv\Scripts\python.exe .\scripts\real-hermes-smoke.py `
  --url http://127.0.0.1:8787 `
  --profile default `
  --write-test
```

This may create one temporary stored session and make one minimal model call. Run it only when that cost and transcript are acceptable.

## Validate every exposed profile

Repeat read-only checks for:

```text
default
mentos
laneb-lab
mql5-forge
agentic-trading
polymarket
```

Expected policy differences:

- `agentic-trading` and `polymarket` are shipped with `jobs_write=false`.
- all six are regular-Hermes profiles;
- no Safety World profile should appear in `/api/profiles` or Administration.

## Live gateway validation

After enabling it:

1. Open **Live Gateway**.
2. Connect to `default`.
3. Verify `gateway.ready` appears.
4. List stored sessions.
5. Resume a non-critical session.
6. Submit a harmless informational prompt.
7. Confirm streamed deltas and terminal event.
8. Disconnect and verify the audit contains ticket, connect and disconnect rows.
9. Attempt to reuse the ticket; it must fail.

## Desktop plugin validation

1. Confirm the plugin is installed only in the regular Hermes home.
2. Restart Hermes Desktop.
3. Enable it in **Capabilities → Plugins** when required by the installed Desktop version.
4. Focus a normal session.
5. Open **Companion** from the sidebar or command palette.
6. Confirm the displayed profile/session matches the focused session.
7. Open the handoff link and sign in.
8. Confirm Companion opens the same stored session.

## Remote-device validation

- Use the private HTTPS URL, never ports 8642/9119.
- Confirm TLS certificate and identity/access policy.
- Install the PWA.
- Sign in with a non-admin test account.
- Verify only assigned profiles appear.
- Revoke the phone from another device and confirm refresh fails.
- Test sleep/reconnect during a harmless run.

## Acceptance checklist

```text
[ ] Bridge health is OK after reboot
[ ] Regular Hermes gateway survives reboot/logon as designed
[ ] Each allowed profile authenticates independently
[ ] Safety World identities are absent
[ ] Durable run stream and reconnect work
[ ] Approve-once / deny policy is enforced
[ ] Device revocation works
[ ] Redacted backup creates and restores
[ ] Upload scanner works when configured
[ ] Live gateway ticket cannot be replayed
[ ] Desktop handoff targets the same stored session
[ ] Remote HTTPS does not expose 8642 or 9119
```
