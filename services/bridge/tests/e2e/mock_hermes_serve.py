from __future__ import annotations

import json
import os
import time

from fastapi import FastAPI, WebSocket

app = FastAPI()
TOKEN = os.getenv("MOCK_HERMES_SERVE_TOKEN", "mock-serve-token-at-least-16")


def response(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def event(kind: str, payload: dict | None = None):
    return {"jsonrpc": "2.0", "method": "event", "params": {"type": kind, "payload": payload or {}}}


@app.websocket("/api/ws")
async def gateway(websocket: WebSocket) -> None:
    if websocket.headers.get("x-hermes-session-token") != TOKEN:
        await websocket.close(code=4401, reason="invalid session token")
        return
    await websocket.accept()
    await websocket.send_text(json.dumps(event("gateway.ready", {"version": "mock", "profile": "default"})))
    session_id = "live-mock-1"
    stored_id = "stored-mock-1"
    messages: list[dict] = []
    try:
        while True:
            raw = await websocket.receive_text()
            for line in raw.splitlines():
                if not line.strip():
                    continue
                frame = json.loads(line)
                request_id = frame.get("id")
                method = frame.get("method")
                params = frame.get("params") or {}
                if method == "client.capabilities":
                    await websocket.send_text(json.dumps(response(request_id, {"accepted": True})))
                elif method == "session.list":
                    await websocket.send_text(json.dumps(response(request_id, {"sessions": [{
                        "id": stored_id, "title": "Mock stored session", "preview": "Live gateway fixture",
                        "started_at": time.time(), "message_count": len(messages), "source": "gui",
                    }]})))
                elif method == "session.create":
                    title = str(params.get("title") or "Mock live session")
                    await websocket.send_text(json.dumps(response(request_id, {
                        "session_id": session_id, "stored_session_id": stored_id,
                        "message_count": 0, "messages": [],
                        "info": {"title": title, "model": "mock:model"},
                    })))
                elif method == "session.resume":
                    await websocket.send_text(json.dumps(response(request_id, {
                        "session_id": session_id, "stored_session_id": stored_id,
                        "message_count": len(messages), "messages": messages,
                        "info": {"title": "Mock stored session", "model": "mock:model"},
                    })))
                elif method == "prompt.submit":
                    text = str(params.get("text") or "")
                    messages.append({"role": "user", "content": text})
                    await websocket.send_text(json.dumps(response(request_id, {"status": "streaming"})))
                    answer = "LIVE_GATEWAY_OK"
                    await websocket.send_text(json.dumps(event("message.delta", {"delta": answer, "session_id": session_id})))
                    messages.append({"role": "assistant", "content": answer})
                    await websocket.send_text(json.dumps(event("message.complete", {"session_id": session_id})))
                    await websocket.send_text(json.dumps(event("turn.completed", {"session_id": session_id, "completed": True})))
                elif method == "session.interrupt":
                    await websocket.send_text(json.dumps(response(request_id, {"interrupted": True})))
                elif method == "ping":
                    await websocket.send_text(json.dumps(response(request_id, {"pong": True})))
                else:
                    await websocket.send_text(json.dumps({
                        "jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32601, "message": f"mock method unavailable: {method}"},
                    }))
    except Exception:
        return
