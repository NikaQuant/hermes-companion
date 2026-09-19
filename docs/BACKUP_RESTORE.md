# Backup and restore

## Two backup classes

| Class | Contains | Use |
|---|---|---|
| **Redacted control-plane backup** | Database without active bearer material, profile policy, manifest | Routine configuration/account backup |
| **Disaster backup** | Optional `.env`, database, policy and uploads | Private full-host recovery |

## Redacted backup from the UI/API

Administrators can create a backup under **Settings**. The archive contains:

```text
manifest.json
hermes_companion.sqlite
profiles.json
```

Before archiving, Companion deletes rows from:

```text
auth_tokens
handoffs
gateway_tickets
```

The archive contains password hashes, user/profile assignments, saved prompts, session metadata, notifications and audit rows. Treat it as confidential even though active tokens and Hermes API keys are absent.

## Command-line backup

Routine redacted archive:

```powershell
.\scripts\backup-local.ps1 -Label before-change
```

Disaster archive:

```powershell
.\scripts\backup-local.ps1 -Label disaster -IncludeSecrets -IncludeUploads
```

`-IncludeSecrets` includes `.env`, therefore Hermes API keys, the Companion app secret and optional live-gateway token. Store it encrypted and offline.

## Restore

1. Stop **Hermes Companion Bridge** and **Hermes Companion Live Gateway**.
2. Copy the backup to the host.
3. Run:

```powershell
.\scripts\restore-backup.ps1 -Archive C:\path\backup.zip
```

The restore tool:

- rejects path traversal and unknown archive members;
- validates the SQLite database;
- preserves a timestamped pre-restore copy;
- restores only known files/directories;
- does not start Safety World components;
- restarts the Companion bridge when requested by the wrapper.

All devices must sign in again after a redacted backup restore.

## Restore compatibility

Backup manifest format `2` is used by v0.3.0. Restore refuses malformed archives. Review [MIGRATION_0.2_TO_0.3.md](MIGRATION_0.2_TO_0.3.md) when restoring across major schema changes.

## Recovery verification

After restore:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
.\.venv\Scripts\python.exe .\scripts\real-hermes-smoke.py --profile default
```

Then sign in and verify users, profile assignments, saved prompts and session metadata.
