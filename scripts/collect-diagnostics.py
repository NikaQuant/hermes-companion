from __future__ import annotations

import argparse
import json
import platform
import re
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_SECRET_LINE = re.compile(r"(?im)^([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)=.*$")
_TOKEN_TEXT = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+")


def redact(text: str) -> str:
    text = _SECRET_LINE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return _TOKEN_TEXT.sub(r"\1<redacted>", text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local redacted Hermes Companion diagnostics ZIP")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = (args.output or root / "artifacts" / f"hermes-companion-diagnostics-{stamp}.zip").resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "created_at": stamp,
        "platform": platform.platform(),
        "python": sys.version,
        "version": (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else "unknown",
        "files": {},
    }
    env_keys: list[str] = []
    env_file = root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                env_keys.append(line.split("=", 1)[0].strip())
    summary["environment_keys"] = sorted(set(env_keys))

    db = root / "services" / "bridge" / "data" / "hermes_companion.db"
    if db.is_file():
        try:
            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
                summary["database"] = {
                    "quick_check": connection.execute("PRAGMA quick_check").fetchone()[0],
                    "tables": [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")],
                }
        except Exception as exc:
            summary["database"] = {"error": type(exc).__name__}

    candidates = [
        root / "VERSION",
        root / "config" / "profiles.json",
        root / "VALIDATION_STATUS.txt",
        root / "BUILD_REPORT.md",
        root / "artifacts" / "validation" / "final-validation.txt",
        root / "logs" / "bridge.log",
    ]
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                archive.writestr(path.relative_to(root).as_posix(), redact(content)[-250_000:])
                summary["files"][path.relative_to(root).as_posix()] = path.stat().st_size
        archive.writestr("diagnostics.json", json.dumps(summary, indent=2) + "\n")
        archive.writestr("README.txt", "This bundle is designed to omit .env values, database rows, prompts, transcripts and uploaded files. Review it before sharing.\n")
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    print(destination)


if __name__ == "__main__":
    main()
