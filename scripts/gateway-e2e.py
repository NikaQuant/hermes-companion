from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import uuid

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus


async def receive_json(socket, *, timeout: float = 10.0) -> dict:
    raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)


async def receive_until(socket, predicate, *, timeout: float = 15.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            frame = await receive_json(socket, timeout=timeout)
            if predicate(frame):
                return frame


async def run(args) -> None:
    base = args.url.rstrip("/")
    email = args.email or input("Companion email: ").strip()
    password = args.password or getpass.getpass("Companion password: ")
    async with httpx.AsyncClient(base_url=base, timeout=20) as client:
        login = await client.post("/api/auth/login", json={
            "email": email, "password": password,
            "device_id": f"gateway-e2e-{uuid.uuid4().hex}", "device_name": "Gateway E2E",
        })
        login.raise_for_status()
        tokens = login.json()
        client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        ticket_response = await client.post(f"/api/gateway/{args.profile}/ticket", json={})
        ticket_response.raise_for_status()
        ticket = ticket_response.json()

    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_base}{ticket['path']}"
    async with connect(ws_url, max_size=2_097_152) as socket:
        ready = await receive_until(socket, lambda f: f.get("method") == "event" and f.get("params", {}).get("type") == "gateway.ready")
        assert ready["params"]["type"] == "gateway.ready"

        await socket.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "client.capabilities", "params": {"server_requests": True}}))
        capabilities = await receive_until(socket, lambda f: f.get("id") == 1)
        assert capabilities.get("result", {}).get("accepted") is True

        await socket.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "config.set", "params": {}}))
        denied = await receive_until(socket, lambda f: f.get("id") == 2)
        assert denied.get("error", {}).get("code") == -32601

        await socket.send(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "session.create", "params": {"profile": args.profile, "source": "e2e", "title": "Gateway E2E"}}))
        created = await receive_until(socket, lambda f: f.get("id") == 3)
        session_id = created.get("result", {}).get("session_id")
        assert session_id

        await socket.send(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "prompt.submit", "params": {"profile": args.profile, "session_id": session_id, "text": "ping"}}))
        submitted = await receive_until(socket, lambda f: f.get("id") == 4)
        assert submitted.get("result", {}).get("status") == "streaming"
        delta = await receive_until(socket, lambda f: f.get("method") == "event" and f.get("params", {}).get("type") == "message.delta")
        assert delta.get("params", {}).get("payload", {}).get("delta") == "LIVE_GATEWAY_OK"
        await receive_until(socket, lambda f: f.get("method") == "event" and f.get("params", {}).get("type") == "turn.completed")

    # A ticket is consumed before the upstream socket is opened and cannot be replayed.
    try:
        async with connect(ws_url) as replay:
            await replay.recv()
        raise AssertionError("one-time ticket replay unexpectedly connected")
    except ConnectionClosed as exc:
        assert exc.code in {4401, 1008}
    except InvalidStatus as exc:
        assert exc.response.status_code in {401, 403}

    print("Hermes Companion live-gateway relay E2E passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise the guarded Hermes serve WebSocket relay")
    parser.add_argument("--url", default=os.getenv("COMPANION_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--email", default=os.getenv("COMPANION_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("COMPANION_PASSWORD", ""))
    parser.add_argument("--profile", default="default")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
