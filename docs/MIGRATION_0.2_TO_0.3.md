# Migration from v0.2 to v0.3

## Summary

v0.3 turns the MVP into a broader control plane. The existing account database is migrated in place; deployment scripts preserve `.env`, database and backups.

## New database features

Migrations add or extend:

- user profile assignments;
- device-aware tokens;
- one-time live-gateway tickets;
- notifications;
- saved prompts;
- session pins/tags/notes;
- upload records;
- audit indexes.

Migrations run automatically on bridge startup.

## Configuration additions

Add or generate these settings:

```text
HERMES_SERVE_URL
HERMES_SERVE_SESSION_TOKEN
GATEWAY_TICKET_SECONDS
GATEWAY_ALLOWED_METHODS
UPLOAD_ROOT
MAX_UPLOAD_BYTES
UPLOAD_RETENTION_DAYS
UPLOAD_SCAN_COMMAND
BACKUP_ROOT
NOTIFICATION_RETENTION_DAYS
```

`generate-env.py` writes appropriate defaults for new installations. Existing `.env` files are preserved, so missing settings use application defaults.

## Profile policy change

`config/profiles.json` now contains operation-level permissions. Review it before deployment. In the shipped policy, Agentic Trading and Polymarket have `jobs_write=false`.

## Frontend change

`apps/web/standalone/` is explicitly the canonical v0.3 PWA source. `apps/web/src/` remains a prototype track and should not be assumed to contain every v0.3 screen.

## Upgrade procedure

```powershell
.\scripts\backup-local.ps1 -Label before-v0.3
.\scripts\upgrade-windows.ps1 -InstallRoot C:\HermesCompanion
```

After health succeeds, run the real-Hermes smoke test and inspect each assigned profile.

## Token behavior

Existing v0.2 tokens may not carry the new device metadata consistently. Use **Logout all** or reset passwords after upgrade when strict device inventory is required.

## Rollback warning

Once the v0.3 database migration has run, older code may not understand all tables/columns. Prefer restoring the pre-upgrade v0.2 database together with the v0.2 application rollback directory rather than running old code against the migrated database.
