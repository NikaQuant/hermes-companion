# Deployment

## Recommended Windows layout

```text
C:\HermesCompanion\
  .env                         server-only secrets
  .venv\                      Python runtime
  services\bridge\data\       SQLite + controlled uploads
  backups\                    Companion backup archives
  logs\bridge.log             bridge runtime log
  apps\web\dist\              built PWA
```

Use the regular Administrator Hermes account. Do not deploy under `HermesSafety` or any `Hermes-Safety` tree.

## First installation

### Extracted-folder installation

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap-windows.ps1
```

### Stable install path with rollback support

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy-windows.ps1 -InstallRoot C:\HermesCompanion
```

The bootstrap:

1. creates `.env` and six profile API keys;
2. creates the initial Companion administrator directly in SQLite;
3. never writes the plaintext administrator password to `.env`;
4. applies Windows ACLs to secrets/data/logs/backups;
5. creates the Python virtual environment;
6. installs the bridge;
7. builds and validates the production PWA;
8. configures Hermes profile multiplexing and keys;
9. installs the regular Desktop plugin;
10. registers and starts the bridge scheduled task;
11. performs a local health check.

## Services and ports

| Port | Service | Bind policy |
|---:|---|---|
| 8787 | Hermes Companion bridge/PWA | Loopback; reverse proxy this service only |
| 8642 | Hermes API | Loopback only |
| 9119 | Optional `hermes serve` | Loopback only |

The bridge scheduled task is `Hermes Companion Bridge`. Its log is `logs\bridge.log`.

## Optional live gateway

```powershell
.\scripts\enable-live-gateway.ps1
```

This creates a random server token, stores it in `.env`, registers `Hermes Companion Live Gateway`, starts `hermes serve` on `127.0.0.1:9119`, and restarts the bridge.

Disable it:

```powershell
.\scripts\disable-live-gateway.ps1
```

## Remote access

### Cloudflare Tunnel

1. Create a tunnel and private hostname.
2. Copy `infra/cloudflared-config.example.yml` into the Cloudflared configuration location.
3. Route the hostname to `http://127.0.0.1:8787`.
4. Add Cloudflare Access or another identity policy.
5. Set the public URL:

```powershell
.\scripts\set-public-url.ps1 -Url https://your-private-hostname.example
Restart-ScheduledTask -TaskName 'Hermes Companion Bridge'
```

### Caddy

Use `infra/caddy/Caddyfile.example` when inbound TLS is available. Caddy terminates HTTPS and proxies only to `127.0.0.1:8787`.

### VPN

Tailscale, WireGuard or another private VPN is valid. Continue to keep 8642 and 9119 unexposed; point clients to the Companion endpoint.

## Upgrade

Extract the new release separately, then run from the new release folder:

```powershell
.\scripts\upgrade-windows.ps1 -InstallRoot C:\HermesCompanion
```

The deployment script:

- stops Companion tasks;
- creates a timestamped rollback copy;
- mirrors new application files while preserving `.env`, `.venv`, data, uploads and backups;
- reruns bootstrap/build/configuration;
- verifies `/api/health`;
- restores the previous code copy if deployment fails.

Rollback copies are intentionally retained until manually removed.

## Uninstall

Preserve data and secrets:

```powershell
.\scripts\uninstall-windows.ps1 -InstallRoot C:\HermesCompanion
```

Remove everything, including Companion account data and backups:

```powershell
.\scripts\uninstall-windows.ps1 -InstallRoot C:\HermesCompanion -RemoveData
```

Hermes itself and Safety World are not removed or modified.

## Post-deployment validation

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
.\.venv\Scripts\python.exe .\scripts\real-hermes-smoke.py --profile default
```

Use `--write-test` only when a temporary Hermes session and one minimal model call are acceptable.
