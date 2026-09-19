from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, processes: list[subprocess.Popen], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"Fixture process exited early with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError(f"Fixture did not become ready: {url}")


def start(command: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> subprocess.Popen:
    handle = log.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT)
    process._hermes_log_handle = handle  # type: ignore[attr-defined]
    return process


def stop(processes: list[subprocess.Popen]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
        handle = getattr(process, "_hermes_log_handle", None)
        if handle:
            handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Hermes Companion against local protocol fixtures")
    parser.add_argument("--browser", action="store_true", help="Run the Playwright desktop/mobile workflow")
    parser.add_argument("--gateway", action="store_true", help="Run the guarded live-gateway workflow")
    parser.add_argument("--artifacts", type=Path, help="Keep logs/screenshots in this directory")
    args = parser.parse_args()
    if not args.browser and not args.gateway:
        args.browser = args.gateway = True

    temp_context = None
    if args.artifacts:
        work = args.artifacts.resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="hermes-companion-fixture-")
        work = Path(temp_context.name)

    api_port, bridge_port, serve_port = free_port(), free_port(), free_port()
    token = "fixture-hermes-serve-token-at-least-16"
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test",
        "APP_SECRET": "fixture-secret-" * 5,
        "DATABASE_PATH": str(work / "bridge.db"),
        "INITIAL_ADMIN_EMAIL": "nik@example.com",
        "INITIAL_ADMIN_PASSWORD": "test-password-long-enough",
        "HERMES_BASE_URL": f"http://127.0.0.1:{api_port}",
        "HERMES_PROFILES_FILE": str(ROOT / "config" / "profiles.json"),
        "WEB_DIST_DIR": str(ROOT / "apps" / "web" / "dist"),
        "UPLOAD_ROOT": str(work / "uploads"),
        "BACKUP_ROOT": str(work / "backups"),
        "HERMES_API_KEY_DEFAULT": "test-key-default",
        "HERMES_API_KEY_MENTOS": "test-key-mentos",
        "HERMES_API_KEY_LANEB_LAB": "test-key-laneb",
        "HERMES_API_KEY_MQL5_FORGE": "test-key-mql5",
        "HERMES_API_KEY_AGENTIC_TRADING": "test-key-agentic",
        "HERMES_API_KEY_POLYMARKET": "test-key-polymarket",
        "HERMES_SERVE_URL": f"http://127.0.0.1:{serve_port}" if args.gateway else "",
        "HERMES_SERVE_SESSION_TOKEN": token if args.gateway else "",
        "MOCK_HERMES_SERVE_TOKEN": token,
    })
    processes: list[subprocess.Popen] = []
    try:
        root_pythonpath = str(ROOT)
        mock_env = env | {"PYTHONPATH": root_pythonpath}
        processes.append(start(
            [sys.executable, "-m", "uvicorn", "services.bridge.tests.e2e.mock_hermes:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=ROOT, env=mock_env, log=work / "mock-http.log",
        ))
        if args.gateway:
            processes.append(start(
                [sys.executable, "-m", "uvicorn", "services.bridge.tests.e2e.mock_hermes_serve:app", "--host", "127.0.0.1", "--port", str(serve_port)],
                cwd=ROOT, env=mock_env, log=work / "mock-serve.log",
            ))
        bridge_env = env | {"PYTHONPATH": str(ROOT / "services" / "bridge")}
        processes.append(start(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(bridge_port)],
            cwd=ROOT / "services" / "bridge", env=bridge_env, log=work / "bridge.log",
        ))
        wait_for(f"http://127.0.0.1:{bridge_port}/api/health", processes)

        common = env | {
            "COMPANION_URL": f"http://127.0.0.1:{bridge_port}",
            "COMPANION_E2E_URL": f"http://127.0.0.1:{bridge_port}",
            "COMPANION_EMAIL": "nik@example.com",
            "COMPANION_PASSWORD": "test-password-long-enough",
            "COMPANION_E2E_EMAIL": "nik@example.com",
            "COMPANION_E2E_PASSWORD": "test-password-long-enough",
            "COMPANION_E2E_SCREENSHOTS": str(work / "screenshots"),
        }
        if args.gateway:
            subprocess.run([sys.executable, "scripts/gateway-e2e.py"], cwd=ROOT, env=common, check=True)
        if args.browser:
            subprocess.run([sys.executable, "scripts/e2e-smoke.py"], cwd=ROOT, env=common, check=True)
        print(f"Fixture artifacts: {work}")
        return 0
    finally:
        stop(processes)
        if temp_context:
            temp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
