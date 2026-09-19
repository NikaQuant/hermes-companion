"""Discover the local Hermes profiles and write config/profiles.json.

Runs `hermes profile list`, keeps every regular profile (Safety World names are
refused), puts `default` first, and writes a profiles.json the bridge understands.
Run this BEFORE generate-env.py so the .env gets one API key per profile.

    python scripts/discover-profiles.py            # write config/profiles.json
    python scripts/discover-profiles.py --print    # show what would be written
    python scripts/discover-profiles.py --only default,mentos
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "config" / "profiles.json"
BLOCKED = {"live-safe", "live_safe", "livesafe", "live-judge", "live_judge", "livejudge",
           "hermes-safety", "hermes_safety", "hermessafety", "safety-world", "safety_world", "safetyworld"}
PALETTE = ["#8b5cf6", "#f59e0b", "#06b6d4", "#10b981", "#ef4444", "#3b82f6", "#ec4899", "#84cc16", "#f97316", "#14b8a6"]
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ROW_RE = re.compile(r"^\s*[◆*>]?\s*(?:(?P<label>[^()]+?)\s*\((?P<slug1>[a-z0-9][a-z0-9_-]*)\)|(?P<slug2>[a-z0-9][a-z0-9_-]*))(?:\s+|$)")


def run_hermes(*args: str) -> str:
    exe = shutil.which("hermes")
    if not exe:
        raise SystemExit("The 'hermes' command is not on PATH. Install Hermes Agent first, then reopen the terminal.")
    result = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"hermes {' '.join(args)} failed:\n{result.stderr or result.stdout}")
    return result.stdout


def parse_profiles(listing: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for line in listing.splitlines():
        if not line.strip() or set(line.strip()) <= set("─- ") or line.lstrip().startswith("Profile"):
            continue
        match = ROW_RE.match(line)
        if not match:
            continue
        slug = (match.group("slug1") or match.group("slug2") or "").strip()
        label = (match.group("label") or slug).strip()
        if not SLUG_RE.match(slug):
            continue
        if slug.lower().replace("_", "-") in BLOCKED or slug.lower().replace("-", "").replace("_", "") in {b.replace("-", "").replace("_", "") for b in BLOCKED}:
            continue
        if slug not in {s for s, _ in found}:
            found.append((slug, label))
    return found


def build(profiles: list[tuple[str, str]]) -> dict:
    ordered = sorted(profiles, key=lambda item: (item[0] != "default", item[0]))
    if not ordered or ordered[0][0] != "default":
        ordered.insert(0, ("default", "Hermes"))
    items = []
    for index, (slug, label) in enumerate(ordered):
        env_name = re.sub(r"[^A-Z0-9]", "_", slug.upper())
        items.append({
            "slug": slug,
            "label": label if slug != "default" or label != "default" else "Hermes",
            "description": f"Hermes profile '{slug}'.",
            "route_prefix": "" if slug == "default" else f"/p/{slug}",
            "api_key_env": f"HERMES_API_KEY_{env_name}",
            "accent": PALETTE[index % len(PALETTE)],
            "permissions": {
                "read": True, "chat": True, "session_write": True, "run_control": True,
                "approval": True, "jobs_write": True, "files_write": True, "gateway_live": True,
            },
            "project_kind": "core" if slug == "default" else "general",
        })
    return {"profiles": items}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--print", action="store_true", help="print instead of writing")
    parser.add_argument("--only", help="comma-separated slugs to keep (default is always included)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing config/profiles.json")
    args = parser.parse_args()

    profiles = parse_profiles(run_hermes("profile", "list"))
    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()} | {"default"}
        profiles = [p for p in profiles if p[0] in keep]
    payload = build(profiles)
    text = json.dumps(payload, indent=2) + "\n"
    if args.print:
        sys.stdout.write(text)
        return 0
    if TARGET.exists() and not args.force:
        existing = json.loads(TARGET.read_text(encoding="utf-8"))
        existing_slugs = [p.get("slug") for p in existing.get("profiles", [])]
        if existing_slugs != ["default"]:
            raise SystemExit(f"{TARGET} already lists {existing_slugs}; re-run with --force to replace it.")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"Wrote {TARGET}")
    for item in payload["profiles"]:
        print(f"  {item['slug']:<20} {item['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
