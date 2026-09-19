from __future__ import annotations

import argparse
import getpass
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _session_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = payload.get("session") or payload.get("data") or payload
    return str(direct.get("id") or direct.get("session_id") or direct.get("stored_session_id") or "") if isinstance(direct, dict) else ""


def _event_name(block: str) -> str:
    for line in block.splitlines():
        if line.startswith("event:"):
            return line.split(":", 1)[1].strip()
        if line.startswith("data:"):
            try:
                payload = json.loads(line.split(":", 1)[1].strip())
                if isinstance(payload, dict) and payload.get("event"):
                    return str(payload["event"])
            except json.JSONDecodeError:
                pass
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a deployed Hermes Companion against the real regular-Hermes gateway")
    parser.add_argument("--url", default=os.getenv("COMPANION_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--email", default=os.getenv("COMPANION_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("COMPANION_PASSWORD", ""))
    parser.add_argument("--profile", default="default")
    parser.add_argument("--write-test", action="store_true", help="Create a temporary session and one minimal model run")
    parser.add_argument("--keep-session", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    email = args.email or input("Companion email: ").strip()
    password = args.password or getpass.getpass("Companion password: ")
    base = args.url.rstrip("/")
    report: dict[str, Any] = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "url": base,
        "profile": args.profile,
        "write_test": args.write_test,
        "checks": [],
    }

    with httpx.Client(base_url=base, timeout=httpx.Timeout(30, read=120), follow_redirects=True) as client:
        def check(name: str, method: str, path: str, **kwargs) -> Any:
            response = client.request(method, path, **kwargs)
            item = {"name": name, "method": method, "path": path, "status": response.status_code, "ok": response.is_success}
            report["checks"].append(item)
            if not response.is_success:
                item["error"] = response.text[:500]
                raise RuntimeError(f"{name} failed: HTTP {response.status_code} {response.text[:300]}")
            if not response.content:
                return None
            return response.json()

        health = check("bridge health", "GET", "/api/health")
        report["version"] = health.get("version") if isinstance(health, dict) else None
        tokens = check("login", "POST", "/api/auth/login", json={
            "email": email,
            "password": password,
            "device_id": f"smoke-{uuid.uuid4().hex}",
            "device_name": f"Real Hermes smoke · {socket.gethostname()}",
        })
        access = tokens["access_token"]
        refresh = tokens.get("refresh_token")
        client.headers["Authorization"] = f"Bearer {access}"

        me = check("identity", "GET", "/api/auth/me")
        profiles = check("profile inventory", "GET", "/api/profiles")
        available = {item["slug"] for item in profiles.get("profiles", []) if item.get("configured")}
        if args.profile not in available:
            raise RuntimeError(f"Profile {args.profile!r} is not configured or assigned to {me.get('email')}")
        check("fleet overview", "GET", "/api/overview")
        check("project overview", "GET", "/api/projects")
        check("sessions", "GET", f"/api/profiles/{args.profile}/sessions?limit=5")
        check("model options", "GET", f"/api/profiles/{args.profile}/model-options")
        check("jobs", "GET", f"/api/profiles/{args.profile}/jobs")

        created_session = ""
        terminal_event = ""
        if args.write_test:
            created = check("create temporary session", "POST", f"/api/profiles/{args.profile}/sessions", json={
                "title": f"Hermes Companion smoke {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
            })
            created_session = _session_id(created)
            if not created_session:
                raise RuntimeError("Hermes did not return a stored session id")
            run = check("start minimal run", "POST", f"/api/profiles/{args.profile}/runs", headers={
                "Idempotency-Key": f"companion-smoke-{uuid.uuid4()}"
            }, json={
                "session_id": created_session,
                "input": "Return exactly COMPANION_SMOKE_OK. Do not call tools and do not perform any external action.",
            })
            run_id = str(run.get("run_id") or run.get("id") or "")
            if not run_id:
                raise RuntimeError("Hermes did not return a run id")
            with client.stream("GET", f"/api/profiles/{args.profile}/runs/{run_id}/events", timeout=None) as response:
                response.raise_for_status()
                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    blocks = buffer.replace("\r\n", "\n").split("\n\n")
                    buffer = blocks.pop() or ""
                    for block in blocks:
                        name = _event_name(block)
                        if name in {"run.completed", "run.failed", "run.cancelled", "run.interrupted", "bridge.error", "bridge.timeout"}:
                            terminal_event = name
                    if terminal_event:
                        break
            report["run"] = {"run_id": run_id, "session_id": created_session, "terminal_event": terminal_event}
            if terminal_event != "run.completed":
                raise RuntimeError(f"Smoke run ended with {terminal_event or 'no terminal event'}")
            check("read completed transcript", "GET", f"/api/profiles/{args.profile}/sessions/{created_session}/messages?limit=20")
            if not args.keep_session:
                check("delete temporary session", "DELETE", f"/api/profiles/{args.profile}/sessions/{created_session}")

        try:
            check("logout", "POST", "/api/auth/logout", json={"refresh_token": refresh})
        except Exception as exc:
            report["logout_warning"] = str(exc)

    report["ok"] = True
    output = args.output or Path(f"hermes-companion-real-smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
