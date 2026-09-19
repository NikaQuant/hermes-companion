from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    printable = " ".join(args)
    print(f"\n> {printable}", flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all validation available on this host")
    parser.add_argument("--gateway-e2e", action="store_true", help="Run the mock hermes serve relay test")
    parser.add_argument("--browser-e2e", action="store_true", help="Run the Playwright browser test (requires Chromium)")
    args = parser.parse_args()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "services" / "bridge")
    run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT / "services" / "bridge", env=env)
    run([sys.executable, "-m", "compileall", "-q", "services/bridge/app", "scripts"])
    run([sys.executable, "scripts/build-web.py"])
    run([sys.executable, "scripts/validate-release.py"] + (["--installed"] if (ROOT / ".env").exists() else []))

    node = shutil.which("node")
    if node:
        run([node, "--check", "apps/web/standalone/app.js"])
        run([node, "--check", "apps/desktop-plugin/plugin.js"])
        for asset in sorted((ROOT / "apps" / "web" / "dist" / "assets").glob("*.js")):
            run([node, "--check", str(asset)])
    else:
        print("Node is unavailable; JavaScript syntax checks were skipped.")

    if args.gateway_e2e:
        run([sys.executable, "scripts/fixture-e2e.py", "--gateway"])
    if args.browser_e2e:
        run([sys.executable, "scripts/fixture-e2e.py", "--browser"])

    print("\nAll requested validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
