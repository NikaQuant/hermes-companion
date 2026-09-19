from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

# Runtime/tooling directories are not part of the shipped release: a virtualenv or
# node_modules installed next to the code must not fail the shipping checks
# (certifi ships cacert.pem inside .venv, which is a legitimate .pem file).
IGNORED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def _scan(root: Path, suffixes: set[str]) -> list[Path]:
    return [
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
        and not IGNORED_PARTS.intersection(path.parts)
    ]


def check(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Hermes Companion release")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="Installed-instance mode: skip shipping-only checks (.env, runtime database, backups)",
    )
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check(bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), "VERSION is not semantic x.y.z")

    json_versions = [
        "package.json",
        "apps/web/package.json",
        "apps/windows/package.json",
        "apps/windows/src-tauri/tauri.conf.json",
    ]
    for name in json_versions:
        data = json.loads((ROOT / name).read_text(encoding="utf-8"))
        check(data.get("version") == version, f"{name} version does not match {version}")

    for name in ("services/bridge/pyproject.toml", "apps/windows/src-tauri/Cargo.toml"):
        data = tomllib.loads((ROOT / name).read_text(encoding="utf-8"))
        section = data.get("project") or data.get("package") or {}
        check(section.get("version") == version, f"{name} version does not match {version}")

    version_source = (ROOT / "services/bridge/app/version.py").read_text(encoding="utf-8")
    check(f'__version__ = "{version}"' in version_source, "Bridge runtime version does not match VERSION")

    dist = ROOT / "apps/web/dist"
    check((dist / "index.html").is_file(), "Production PWA index is missing; run scripts/build-web.py")
    if (dist / "index.html").is_file():
        index = (dist / "index.html").read_text(encoding="utf-8")
        js_refs = re.findall(r'src="(/assets/[^"]+\.js)"', index)
        css_refs = re.findall(r'href="(/assets/[^"]+\.css)"', index)
        check(len(js_refs) == 1, "Production index must reference exactly one JavaScript bundle")
        check(len(css_refs) == 1, "Production index must reference exactly one CSS bundle")
        for ref in js_refs + css_refs:
            check((dist / ref.lstrip("/")).is_file(), f"Missing referenced asset: {ref}")
    else:
        js_refs, css_refs = [], []

    manifest_path = dist / "manifest.webmanifest"
    check(manifest_path.is_file(), "PWA manifest is missing")
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check(manifest.get("version") == version, "PWA manifest version mismatch")
    check((dist / "sw.js").is_file(), "PWA service worker is missing")

    profiles = json.loads((ROOT / "config/profiles.json").read_text(encoding="utf-8")).get("profiles", [])
    slugs = [str(item.get("slug", "")) for item in profiles]
    check(bool(slugs) and slugs[0] == "default", "config/profiles.json must list the 'default' profile first")
    check(len(slugs) == len(set(slugs)), "Duplicate profile slug")
    check(all(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", s or "") for s in slugs), "Invalid profile slug in profiles.json")
    check(all(str(item.get("api_key_env", "")).startswith("HERMES_API_KEY_") for item in profiles), "Every profile needs api_key_env=HERMES_API_KEY_<NAME>")
    compact = {slug.lower().replace("-", "").replace("_", "").replace(" ", "") for slug in slugs}
    check(
        not compact.intersection({"livesafe", "livejudge", "hermessafety", "safetyworld"}),
        "Safety World profile appeared in the release allowlist",
    )

    required_docs = (
        "README.md",
        "QUICK_START.txt",
        "BUILD_REPORT.md",
        "DELIVERY.md",
        "CHANGELOG.md",
        "VALIDATION_STATUS.txt",
        "docs/README.md",
        "docs/ARCHITECTURE.md",
        "docs/SECURITY.md",
        "docs/DEPLOYMENT.md",
        "docs/USER_GUIDE.md",
        "docs/ADMIN_GUIDE.md",
        "docs/LIVE_GATEWAY.md",
        "docs/FILES.md",
        "docs/BACKUP_RESTORE.md",
        "docs/OPERATIONS_RUNBOOK.md",
        "docs/REAL_HERMES_VALIDATION.md",
        "docs/API_REFERENCE.md",
        "docs/THREAT_MODEL.md",
        "docs/NATIVE_BUILDS.md",
        "docs/DESKTOP_PLUGIN.md",
        "docs/MIGRATION_0.2_TO_0.3.md",
        "docs/LIMITATIONS.md",
    )
    for name in required_docs:
        check((ROOT / name).is_file(), f"Required documentation is missing: {name}")

    required_artifacts = (
        "artifacts/README.md",
        "artifacts/e2e/command-center.png",
        "artifacts/e2e/chat-run.png",
        "artifacts/e2e/mobile-command-center.png",
        "artifacts/e2e/mobile-chat.png",
        "artifacts/validation/browser-validation.txt",
        "artifacts/validation/gateway-validation.txt",
        "artifacts/validation/backup-restore-validation.txt",
        "artifacts/validation/real-smoke-fixture-validation.txt",
    )
    for name in required_artifacts:
        check((ROOT / name).is_file(), f"Required validation artifact is missing: {name}")

    if not args.installed:
        check(not (ROOT / ".env").exists(), "A real .env file must not be shipped")
    check((ROOT / ".env.example").is_file(), ".env.example is missing")
    runtime_suffixes = {".db", ".sqlite", ".sqlite3", ".wal", ".shm"}
    runtime_files = _scan(ROOT, runtime_suffixes)
    check(not runtime_files or args.installed, "Runtime database/journal files must not be shipped")
    secret_suffixes = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
    secret_files = _scan(ROOT, secret_suffixes)
    check(not secret_files, "Private signing/key material must not be shipped")
    backup_payloads = [path for path in (ROOT / "backups").glob("*") if path.is_file()]
    check(not backup_payloads or args.installed, "Runtime backup archives must not be shipped")

    if ERRORS:
        for error in ERRORS:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"Release validation passed for Hermes Companion {version}")
    print(f"Profiles: {', '.join(slugs)}")
    print(f"Web assets: {len(js_refs)} JS, {len(css_refs)} CSS, manifest + service worker")
    print(f"Documentation: {len(required_docs)} required files")
    print(f"Validation artifacts: {len(required_artifacts)} required files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
