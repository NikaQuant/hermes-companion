from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIR_NAMES = {
    ".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "target", ".gradle", ".hermes",
}
EXCLUDED_FILES = {".env", "local.properties", ".DS_Store", "Thumbs.db", ".private-markers.txt"}
EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".log", ".sqlite", ".sqlite3", ".db", ".wal", ".shm",
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".bak",
}
# Anything that could identify the machine this release was built on lives OUTSIDE the
# shipped tree in scripts/.private-markers.txt (one lowercase substring per line; gitignored,
# never copied). Without the file the scan is skipped with a warning.
_MARKERS_FILE = ROOT / "scripts" / ".private-markers.txt"
PRIVATE_MARKERS = tuple(
    line.strip().lower()
    for line in (_MARKERS_FILE.read_text(encoding="utf-8").splitlines() if _MARKERS_FILE.exists() else [])
    if line.strip() and not line.startswith("#")
)

GENERIC_PROFILES = {
    "profiles": [
        {
            "slug": "default",
            "label": "Hermes",
            "description": "Your main Hermes profile.",
            "route_prefix": "",
            "api_key_env": "HERMES_API_KEY_DEFAULT",
            "accent": "#8b5cf6",
            "permissions": {
                "read": True, "chat": True, "session_write": True, "run_control": True,
                "approval": True, "jobs_write": True, "files_write": True, "gateway_live": True,
            },
            "project_kind": "core",
        }
    ]
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_skip(relative: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in relative.parts):
        return True
    if relative.name in EXCLUDED_FILES or relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    text = relative.as_posix()
    if text.startswith("services/bridge/data/") or text.startswith("backups/") or text.startswith("logs/"):
        return True
    if text.startswith("apps/web/android/app/build/"):
        return True
    if text.startswith("artifacts/validation/real-host-") or text.startswith("artifacts/hermes-companion-diagnostics"):
        return True
    if relative.name.startswith(".env.bak"):
        return True
    if text.endswith(".zip"):
        return True
    return False


def scrub_stage(stage: Path) -> list[str]:
    """Replace the builder's profiles.json with a generic one and scan for private markers."""
    import json

    (stage / "config" / "profiles.json").write_text(json.dumps(GENERIC_PROFILES, indent=2) + "\n", encoding="utf-8")
    leaks: list[str] = []
    if not PRIVATE_MARKERS:
        print("WARNING: scripts/.private-markers.txt missing - private-data scan skipped")
        return leaks
    for path in stage.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for marker in PRIVATE_MARKERS:
            if marker in content:
                leaks.append(f"{path.relative_to(stage).as_posix()} contains '{marker}'")
    return leaks


def copy_release_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(source)
        if should_skip(relative):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def zip_tree(source: Path, destination: Path, *, root_name: str | None = None) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            arcname = Path(root_name) / relative if root_name else relative
            archive.write(path, arcname.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Create clean Hermes Companion release archives")
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    release_name = f"Hermes-Companion-v{version}"

    with tempfile.TemporaryDirectory(prefix="hermes-companion-release-") as temp:
        stage = Path(temp) / release_name
        stage.mkdir()
        copy_release_tree(ROOT, stage)
        leaks = scrub_stage(stage)
        if leaks:
            for leak in leaks:
                print(f"PRIVATE DATA: {leak}")
            print("Refusing to build a release that contains machine-specific data.")
            return 1
        # Rebuild the PWA inside the stage so dist matches the shipped source exactly.
        import subprocess, sys
        subprocess.run([sys.executable, str(stage / "scripts" / "build-web.py")], check=True, cwd=stage)

        full_zip = output / f"{release_name}-built.zip"
        pwa_zip = output / f"{release_name}-PWA.zip"
        docs_zip = output / f"{release_name}-Docs.zip"
        for path in (full_zip, pwa_zip, docs_zip):
            path.unlink(missing_ok=True)

        zip_tree(stage, full_zip, root_name=release_name)

        pwa_stage = Path(temp) / "pwa"
        shutil.copytree(stage / "apps" / "web" / "dist", pwa_stage)
        (pwa_stage / "README.txt").write_text(
            "Hermes Companion PWA build. Serve these files from the Companion bridge or another "
            "HTTPS origin; the API still requires the Companion FastAPI bridge.\n",
            encoding="utf-8",
        )
        zip_tree(pwa_stage, pwa_zip)

        docs_stage = Path(temp) / "docs"
        docs_stage.mkdir()
        shutil.copytree(stage / "docs", docs_stage / "docs")
        for name in ("README.md", "QUICK_START.txt", "BUILD_REPORT.md", "DELIVERY.md", "CHANGELOG.md", "VALIDATION_STATUS.txt"):
            source = stage / name
            if source.is_file():
                shutil.copy2(source, docs_stage / name)
        zip_tree(docs_stage, docs_zip, root_name=f"{release_name}-Docs")

    sums = output / f"{release_name}-SHA256SUMS.txt"
    lines = [f"{sha256(path)}  {path.name}" for path in (full_zip, pwa_zip, docs_zip)]
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for path in (full_zip, pwa_zip, docs_zip, sums):
        print(f"{path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
