# Operations runbook

## Service inventory

| Service | Task / port | Required |
|---|---|---|
| Companion bridge | `Hermes Companion Bridge` / `127.0.0.1:8787` | Yes |
| Hermes API listener | Hermes gateway / `127.0.0.1:8642` | Yes for Hermes operations |
| Optional live gateway | `Hermes Companion Live Gateway` / `127.0.0.1:9119` | No |
| Reverse proxy / tunnel | Private HTTPS endpoint | Only for remote devices |

## Daily health check

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
Get-ScheduledTask -TaskName 'Hermes Companion Bridge','Hermes Companion Live Gateway'
Get-Content .\logs\bridge.log -Tail 100
```

In the UI, inspect **Command Center** and **Projects** for per-profile health.

## Start and stop

```powershell
Start-ScheduledTask -TaskName 'Hermes Companion Bridge'
Stop-ScheduledTask  -TaskName 'Hermes Companion Bridge'

Start-ScheduledTask -TaskName 'Hermes Companion Live Gateway'
Stop-ScheduledTask  -TaskName 'Hermes Companion Live Gateway'
```

## Logs

Bridge log:

```text
logs/bridge.log
```

The launcher rotates the log when it grows beyond approximately 10 MiB. Hermes gateway/Desktop logs remain in the regular Hermes home and are not copied into Companion by default.

## Upgrade

1. Create a redacted and, when appropriate, disaster backup.
2. Extract the new release outside the live install directory.
3. From the new release run:

```powershell
.\scripts\upgrade-windows.ps1 -InstallRoot C:\HermesCompanion
```

The deploy script retains a timestamped rollback directory, mirrors application files, preserves `.env`, database and backups, reruns migrations/build, and checks local health.

## Rollback

If automated rollback does not complete:

1. Stop Companion tasks.
2. Rename the failed install directory.
3. Rename the latest `C:\HermesCompanion.rollback-<timestamp>` to `C:\HermesCompanion`.
4. Start the bridge task.
5. Run the health and real-Hermes smoke checks.

## Lost administrator password

Use the local reset tool while logged into the Windows account that owns the installation. This is a host-admin recovery path and must not be exposed through a remote unauthenticated endpoint.

## Database problem

1. Stop the bridge.
2. Preserve the database and `-wal`/`-shm` files before changing anything.
3. Run SQLite `PRAGMA quick_check` using Python or the diagnostics script.
4. Restore the latest known-good backup if integrity fails.
5. Do not copy a live WAL database without the provided SQLite backup procedure.

## Run stuck or disconnected

- Reopen **Chat**; Companion reconnects using the stored run ID.
- Fetch `GET /api/profiles/{profile}/runs/{run_id}` through the UI/client.
- Use **Stop** if the run is still active and policy permits.
- If the gateway restarted, Hermes may report the run as interrupted rather than resumable.

## Optional live gateway failure

1. Confirm task state.
2. Confirm `HERMES_SERVE_URL=http://127.0.0.1:9119` and token is non-empty in `.env` without sharing its value.
3. Confirm local `http://127.0.0.1:9119/api/status` or the appropriate Hermes status route is reachable.
4. Disable and re-enable the live gateway to rotate the token and task definition.
5. Durable HTTP runs remain available while this feature is disabled.

## Security incident

For a lost phone or suspected token theft:

1. Revoke the device or use **Logout all**.
2. Change the Companion password.
3. Review the audit log by time, user and profile.
4. Rotate `APP_SECRET` only when prepared to invalidate all signed state.
5. Rotate affected Hermes profile API keys if bridge `.env` exposure is suspected.
6. Rotate `HERMES_SERVE_SESSION_TOKEN` by disabling/re-enabling live gateway.
7. Review reverse-proxy/tunnel logs.
8. Preserve diagnostics and logs before cleanup.

## Disk cleanup

- Delete obsolete redacted backups through the UI.
- Remove old rollback directories after successful verification.
- Review upload retention and backup copies.
- Never delete the active database while the bridge is running.
