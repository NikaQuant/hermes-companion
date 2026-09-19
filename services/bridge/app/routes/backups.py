from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ..dependencies import client_ip, require_admin, state
from ..schemas import BackupCreateRequest
from ..version import __version__


router = APIRouter(prefix="/api/backups", tags=["backups"])
_SAFE_LABEL = re.compile(r"[^A-Za-z0-9._-]+")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unlink_quietly(path: Path) -> None:
    """Windows: unlink fails while any handle is open (e.g. antivirus scanning)."""
    for attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    logging.getLogger("hermes_companion").warning("Could not remove temporary backup database: %s", path)


def _backup_files(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("hermes-companion-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        result.append({
            "name": path.name,
            "bytes": stat.st_size,
            "created_at": int(stat.st_mtime),
        })
    return result


@router.get("")
def list_backups(request: Request, _admin: dict = Depends(require_admin)) -> dict:
    return {"backups": _backup_files(state(request).settings.backup_root)}


@router.post("")
def create_backup(
    request: Request, body: BackupCreateRequest, admin: dict = Depends(require_admin)
) -> dict:
    app = state(request)
    app.settings.backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = _SAFE_LABEL.sub("-", body.label.strip()).strip("-.")[:40] or "manual"
    base = f"hermes-companion-{stamp}-{label}"
    temp_db = app.settings.backup_root / f".{base}.sqlite"
    destination = app.settings.backup_root / f"{base}.zip"
    app.db.backup_to(temp_db)
    # One-time bearer material is deliberately omitted. Password hashes and user/profile
    # configuration remain so the archive can restore the control plane, but every device
    # must sign in again after a restore.
    # sqlite3 connection `with` blocks commit but do NOT close; close explicitly so the
    # unlink below succeeds on Windows (WinError 32 while a handle is open).
    connection = sqlite3.connect(temp_db)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        for table in ("auth_tokens", "handoffs", "gateway_tickets"):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
        check = connection.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError("Backup database integrity check failed")
    finally:
        connection.close()

    manifest = {
        "format": 2,
        "created_at": stamp,
        "version": __version__,
        "database": "hermes_companion.sqlite",
        "profiles": "profiles.json",
        "contains_hermes_api_keys": False,
        "contains_raw_tokens": False,
        "contains_password_hashes": True,
        "device_sessions_revoked": True,
        "restore": "Stop Companion and run scripts/restore-backup.py against this archive.",
        "files": [
            {
                "path": "hermes_companion.sqlite",
                "bytes": temp_db.stat().st_size,
                "sha256": _sha256(temp_db),
            },
            {
                "path": "profiles.json",
                "bytes": app.settings.hermes_profiles_file.stat().st_size,
                "sha256": _sha256(app.settings.hermes_profiles_file),
            },
        ],
    }
    try:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(temp_db, "hermes_companion.sqlite")
            archive.write(app.settings.hermes_profiles_file, "profiles.json")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    finally:
        _unlink_quietly(temp_db)
    app.db.audit(
        event="backup.created", user_id=admin["id"], ip=client_ip(request),
        metadata={"name": destination.name, "bytes": destination.stat().st_size},
    )
    return {"name": destination.name, "bytes": destination.stat().st_size, "created_at": int(destination.stat().st_mtime)}


@router.get("/{name}")
def download_backup(request: Request, name: str, _admin: dict = Depends(require_admin)):
    if Path(name).name != name or not name.startswith("hermes-companion-") or not name.endswith(".zip"):
        raise HTTPException(status_code=404, detail="Backup not found")
    path = (state(request).settings.backup_root / name).resolve()
    try:
        path.relative_to(state(request).settings.backup_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Backup not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/zip", filename=name, headers={"Cache-Control": "private, no-store"})


@router.delete("/{name}")
def delete_backup(
    request: Request, name: str, admin: dict = Depends(require_admin)
) -> dict:
    if Path(name).name != name or not name.startswith("hermes-companion-") or not name.endswith(".zip"):
        raise HTTPException(status_code=404, detail="Backup not found")
    path = (state(request).settings.backup_root / name).resolve()
    try:
        path.relative_to(state(request).settings.backup_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Backup not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    size = path.stat().st_size
    path.unlink()
    state(request).db.audit(
        event="backup.deleted", user_id=admin["id"], ip=client_ip(request),
        metadata={"name": name, "bytes": size},
    )
    return {"ok": True}
