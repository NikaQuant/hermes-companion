# Administrator guide

## Administrative model

Companion has two roles:

| Role | Scope |
|---|---|
| `admin` | All configured Companion profiles, user management, audit, backups and diagnostics |
| `user` | Only explicitly assigned profiles; no user administration or backup access |

An empty profile assignment for an administrator means all configured profiles. An empty assignment for an ordinary user means no profiles.

## Initial administrator

`scripts/generate-env.py` creates the initial administrator directly in the local database. The plaintext password is entered interactively and is not retained in `.env`.

Production passwords must contain at least 12 characters. Use a unique password that is not shared with Hermes, Windows or Nous Portal.

## Create a user

From **Administration**:

1. Enter the user's email.
2. Set a temporary unique password.
3. Choose `user` or `admin`.
4. Assign regular-Hermes profiles.
5. Create the account.

Safety World aliases are rejected even if manually submitted to the API.

## Profile assignments

User access is the intersection of:

```text
configured profile
∩ profile operation permission
∩ user profile assignment
∩ endpoint-specific authorization
```

A visible profile does not imply unrestricted control. For example, `jobs_write=false` permits reading jobs but blocks create, update, run, pause, resume and delete through Companion.

## Operation permissions

`config/profiles.json` supports:

| Permission | Controls |
|---|---|
| `read` | Health, sessions, messages, jobs, models and project summaries |
| `chat` | Start durable runs |
| `session_write` | Create, rename, fork and delete sessions |
| `run_control` | Stop and steer runs |
| `approval` | Resolve pending run approvals |
| `jobs_write` | Create, edit, run, pause, resume and delete jobs |
| `files_write` | Upload and delete controlled files |
| `gateway_live` | Obtain a ticket for the optional live WebSocket relay |

Changing this file requires a bridge restart.

## Disable or delete users

Disabling a user revokes effective access while preserving account history. Deleting a user removes the account and its Companion-owned records. The current administrator cannot disable, demote or delete itself, and the final active administrator cannot be deleted.

## Reset a password

An administrator can set a replacement password. All of that user's access and refresh tokens are revoked.

Local emergency reset:

```powershell
.\.venv\Scripts\python.exe .\scripts\reset-admin-password.py `
  --database .\services\bridge\data\hermes_companion.db `
  --email admin@example.com
```

Use the wrapper `scripts/reset-admin-password.ps1` where appropriate.

## Devices

Each login is associated with a device ID and device name. Refresh-token rotation remains bound to that device. Revoke lost or retired devices immediately.

`Logout all` invalidates all account tokens, including the current device.

## Audit

The audit log records security-relevant Companion actions, including:

- login failures and successes;
- refresh, logout and device revocation;
- user creation/update/deletion;
- session changes;
- run start, stop, steer and approval;
- file upload/delete;
- backup creation/deletion;
- gateway ticket and connection lifecycle.

Audit metadata is intentionally bounded. Do not add full prompts, model output, passwords, API keys or uploaded file contents to audit metadata.

## Backups

The in-app backup route creates a token-scrubbed archive containing:

- Companion database;
- profile policy file;
- restore manifest.

It removes access tokens, refresh tokens, handoffs and gateway tickets. Password hashes remain so accounts survive, but all devices must sign in again.

For full host disaster recovery including `.env` and uploads, use `scripts/backup-local.ps1 -IncludeSecrets -IncludeUploads` and protect that archive as a secret.

## Diagnostics

The diagnostics API and bundle script are designed to omit:

- `.env` values;
- database rows;
- prompts and transcripts;
- uploaded file contents;
- Hermes API keys.

Always inspect a bundle before sharing it.

## Recommended production settings

```text
APP_ENV=production
APP_SECRET=<32+ random bytes>
TRUST_PROXY_HEADERS=false  # true only behind a trusted, sanitizing proxy
ALLOW_WIDE_APPROVALS=false
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_SERVE_URL=http://127.0.0.1:9119  # optional
```

Use private HTTPS, a VPN or an identity-aware tunnel for remote access. Do not publish Hermes ports directly.
