from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


_ALLOWED_TOP_LEVEL = {"manifest.json", "hermes_companion.sqlite", "profiles.json", "VERSION", ".env"}


def _validate_member(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        raise ValueError(f"Unsafe archive member: {name}")
    if normalized not in _ALLOWED_TOP_LEVEL and not normalized.startswith("uploads/"):
        raise ValueError(f"Unexpected archive member: {name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_manifest_files(temp: Path, manifest: dict) -> None:
    entries = list(manifest.get("files") or []) + [
        {**item, "path": f"uploads/{item.get('path', '')}"}
        for item in (manifest.get("uploads") or [])
    ]
    for item in entries:
        name = str(item.get("path") or "")
        _validate_member(name)
        path = temp / name
        if not path.is_file():
            raise ValueError(f"Manifest file is missing: {name}")
        if item.get("bytes") is not None and path.stat().st_size != int(item["bytes"]):
            raise ValueError(f"Manifest size mismatch: {name}")
        expected = str(item.get("sha256") or "")
        if expected and _sha256(path) != expected:
            raise ValueError(f"Manifest digest mismatch: {name}")


def _validate_database(path: Path) -> None:
    # Explicit close: `with sqlite3.connect(...)` commits but does NOT close, and on
    # Windows the open handle makes TemporaryDirectory cleanup fail (WinError 32).
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        check = connection.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            raise ValueError("Backup SQLite database failed quick_check")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "users" not in tables or "audit_log" not in tables:
            raise ValueError("Archive is not a Hermes Companion database")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a Hermes Companion backup archive")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--restore-profiles", action="store_true")
    parser.add_argument("--restore-env", action="store_true")
    parser.add_argument("--restore-uploads", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    archive_path = args.archive.resolve()
    if not archive_path.is_file():
        raise SystemExit(f"Backup not found: {archive_path}")
    sys.path.insert(0, str(root / "services" / "bridge"))
    from app.config import Settings

    settings = Settings.from_env(project_root=root, env_file=root / ".env")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    with tempfile.TemporaryDirectory(prefix="hermes-companion-restore-") as temp_value:
        temp = Path(temp_value)
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                _validate_member(info.filename)
            if "manifest.json" not in archive.namelist() or "hermes_companion.sqlite" not in archive.namelist():
                raise SystemExit("Archive is missing manifest.json or hermes_companion.sqlite")
            manifest = json.loads(archive.read("manifest.json"))
            if int(manifest.get("format", 0)) not in {1, 2}:
                raise SystemExit(f"Unsupported backup format: {manifest.get('format')}")
            archive.extractall(temp)

        _validate_manifest_files(temp, manifest)
        restored_db = temp / "hermes_companion.sqlite"
        _validate_database(restored_db)
        if not args.force:
            answer = input(f"Replace Companion database at {settings.database_path}? Type RESTORE: ")
            if answer != "RESTORE":
                raise SystemExit("Restore cancelled")

        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        if settings.database_path.exists():
            rollback = settings.database_path.with_name(
                f"{settings.database_path.name}.pre-restore-{stamp}.bak"
            )
            shutil.copy2(settings.database_path, rollback)
            print(f"Current database preserved at {rollback}")
        staging = settings.database_path.with_suffix(settings.database_path.suffix + ".restore")
        shutil.copy2(restored_db, staging)
        os.replace(staging, settings.database_path)

        if args.restore_profiles and (temp / "profiles.json").is_file():
            backup = settings.hermes_profiles_file.with_name(
                f"{settings.hermes_profiles_file.name}.pre-restore-{stamp}.bak"
            )
            if settings.hermes_profiles_file.exists():
                shutil.copy2(settings.hermes_profiles_file, backup)
            shutil.copy2(temp / "profiles.json", settings.hermes_profiles_file)

        if args.restore_env:
            env_source = temp / ".env"
            if not env_source.is_file():
                raise SystemExit("Archive does not contain .env")
            env_target = root / ".env"
            if env_target.exists():
                shutil.copy2(env_target, root / f".env.pre-restore-{stamp}.bak")
            shutil.copy2(env_source, env_target)

        if args.restore_uploads:
            upload_source = temp / "uploads"
            if not upload_source.is_dir():
                raise SystemExit("Archive does not contain uploads")
            settings.upload_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(upload_source, settings.upload_root, dirs_exist_ok=True)

    print("Restore completed. Restart the Hermes Companion Bridge task.")
    if manifest.get("device_sessions_revoked", True):
        print("Every client must sign in again because device tokens were removed from the backup.")


if __name__ == "__main__":
    main()
