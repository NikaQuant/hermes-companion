"""Wire the local Hermes profiles to the Companion bridge (Windows/Linux/macOS).

For every profile in config/profiles.json this script:
  1. asks `hermes profile show <slug>` for that profile's home directory,
  2. writes API_SERVER_KEY=<key from .env> into that profile's .env
     (API_SERVER_ENABLED=true ONLY for the default profile - it is the single listener),
  3. keeps a timestamped .env.bak-* backup,
then enables gateway.multiplex_profiles on the default profile and (re)starts its gateway.

Keys are read from the Companion .env in-process and never printed.

    python scripts/wire-hermes.py            # do it
    python scripts/wire-hermes.py --dry-run  # show the plan only
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def upsert_env(path: Path, updates: dict[str, str], dry_run: bool) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.partition("=")[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    if dry_run:
        return
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%dT%H%M%S')}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def hermes(*args: str, check: bool = True) -> str:
    exe = shutil.which("hermes")
    if not exe:
        raise SystemExit("The 'hermes' command is not on PATH.")
    result = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise SystemExit(f"hermes {' '.join(args)} failed ({result.returncode}):\n{result.stderr or result.stdout}")
    return result.stdout + result.stderr


def profile_home(slug: str) -> Path:
    text = hermes("profile", "show", slug)
    match = re.search(r"^\s*Path:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not read the home directory of profile '{slug}' from `hermes profile show`.")
    return Path(match.group(1).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-restart", action="store_true", help="skip gateway install/restart")
    args = parser.parse_args()

    companion_env = read_env(ROOT / ".env")
    if not companion_env:
        raise SystemExit("Missing .env - run scripts/generate-env.py first.")
    profiles = json.loads((ROOT / "config" / "profiles.json").read_text(encoding="utf-8"))["profiles"]

    plan: list[tuple[str, Path, dict[str, str]]] = []
    for item in profiles:
        slug = item["slug"]
        key = companion_env.get(item["api_key_env"], "")
        if len(key) < 16:
            print(f"skip {slug}: no key {item['api_key_env']} in .env (profile stays 'not connected')")
            continue
        try:
            home = profile_home(slug)
        except SystemExit as exc:
            print(f"skip {slug}: {exc}")
            continue
        updates = {"API_SERVER_KEY": key}
        if slug == "default":
            updates["API_SERVER_ENABLED"] = "true"
        else:
            updates["API_SERVER_ENABLED"] = "false"
        plan.append((slug, home / ".env", updates))

    if not plan:
        raise SystemExit("Nothing to wire: no profile matched a key in .env.")
    for slug, env_path, updates in plan:
        print(f"{'would write' if args.dry_run else 'writing'} {sorted(updates)} -> {env_path}  ({slug})")
        upsert_env(env_path, updates, args.dry_run)

    if args.dry_run:
        print("dry run: gateway not touched")
        return 0
    print(hermes("-p", "default", "config", "set", "gateway.multiplex_profiles", "true").strip())
    if not args.no_restart:
        status = hermes("-p", "default", "gateway", "status", check=False)
        if "running" in status.lower():
            print(hermes("-p", "default", "gateway", "restart", check=False).strip())
        else:
            print(hermes("-p", "default", "gateway", "install", check=False).strip())
            print(hermes("-p", "default", "gateway", "start", check=False).strip())
    print("Wired", ", ".join(slug for slug, _, _ in plan))
    print("Verify: python scripts/real-hermes-smoke.py --url http://127.0.0.1:8787 --profile default")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
