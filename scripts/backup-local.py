from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned[:48] or "manual"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scrub_ephemeral_tokens(database: Path) -> None:
    # Explicit close: `with sqlite3.connect(...)` commits but does NOT close, and on
    # Windows the open handle makes TemporaryDirectory cleanup fail (WinError 32).
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        for table in ("auth_tokens", "handoffs", "gateway_tickets"):
            try:
                connection.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        connection.commit()
        check = connection.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError("SQLite quick_check failed")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an offline Hermes Companion backup archive. The archive is sensitive."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--label", default="manual")
    parser.add_argument("--include-env", action="store_true", help="Include .env and Hermes API keys")
    parser.add_argument("--include-uploads", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    sys.path.insert(0, str(root / "services" / "bridge"))
    from app.config import Settings
    from app.db import Database
    from app.version import __version__

    settings = Settings.from_env(project_root=root, env_file=root / ".env")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "full" if args.include_env else "redacted"
    output_dir = (args.output or (root / "backups")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"hermes-companion-{stamp}-{_safe_label(args.label)}-{suffix}.zip"

    with tempfile.TemporaryDirectory(prefix="hermes-companion-backup-") as temp_value:
        temp = Path(temp_value)
        database = temp / "hermes_companion.sqlite"
        Database(settings.database_path).backup_to(database)
        if not args.include_env:
            _scrub_ephemeral_tokens(database)

        files: list[tuple[Path, str]] = [
            (database, "hermes_companion.sqlite"),
            (settings.hermes_profiles_file, "profiles.json"),
            (root / "VERSION", "VERSION"),
        ]
        if args.include_env:
            env_file = root / ".env"
            if not env_file.is_file():
                raise SystemExit("--include-env requested but .env is missing")
            files.append((env_file, ".env"))

        upload_manifest: list[dict[str, object]] = []
        if args.include_uploads and settings.upload_root.is_dir():
            for path in sorted(settings.upload_root.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(settings.upload_root).as_posix()
                    upload_manifest.append({
                        "path": relative,
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    })

        manifest = {
            "format": 2,
            "created_at": stamp,
            "version": __version__,
            "backup_kind": suffix,
            "contains_hermes_api_keys": bool(args.include_env),
            "contains_raw_tokens": bool(args.include_env),
            "contains_password_hashes": True,
            "device_sessions_revoked": not args.include_env,
            "includes_uploads": bool(args.include_uploads),
            "files": [
                {"path": archive_name, "bytes": source.stat().st_size, "sha256": _sha256(source)}
                for source, archive_name in files
            ],
            "uploads": upload_manifest,
        }

        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source, archive_name in files:
                archive.write(source, archive_name)
            if args.include_uploads and settings.upload_root.is_dir():
                for item in upload_manifest:
                    source = settings.upload_root / str(item["path"])
                    archive.write(source, f"uploads/{item['path']}")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")

    try:
        destination.chmod(0o600)
    except OSError:
        pass
    print(destination)
    print(f"sha256={_sha256(destination)}")
    print("WARNING: this archive contains Companion account data and must be stored privately.")
    if args.include_env:
        print("WARNING: full backup includes Hermes API keys and APP_SECRET in plaintext inside the ZIP.")


if __name__ == "__main__":
    main()
