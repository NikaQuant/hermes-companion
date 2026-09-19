from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ..dependencies import client_ip, current_user, get_profile, state
from ..security import new_token


router = APIRouter(prefix="/api/gateway", tags=["live-gateway"])

_BLOCKED_COMMAND_PREFIXES = (
    "/terminal", "/shell", "/exec", "/bash", "/powershell", "/config", "/profile",
    "/gateway", "/update", "/uninstall", "/install", "/mcp", "/plugin", "/plugins",
    "/serve", "/dashboard",
)
_ATTACHMENT_METHODS = {"image.attach", "pdf.attach", "file.attach"}
_RAW_ATTACHMENT_METHODS = {"image.attach_bytes", "input.detect_drop"}


def _upstream_ws_url(base: str, session_token: str = "") -> str:
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https", "ws", "wss"}:
        raise ValueError("HERMES_SERVE_URL must use http, https, ws, or wss")
    scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    path = parsed.path.rstrip("/") + "/api/ws"
    query = parsed.query
    if session_token:
        # hermes serve authenticates its loopback WebSocket with ?token= (compared
        # constant-time against its session token); it does NOT read an auth header
        # on the upgrade. The X-Hermes-Session-Token header is still sent at connect
        # time below — it matches the mock-fixture contract and is ignored by serve.
        query = (query + "&" if query else "") + "token=" + quote(session_token, safe="")
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))


def _rpc_error(request_id, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _validate_client_frame(app, user: dict, profile: str, raw: str, open_requests: set[str]) -> str | None:
    if len(raw.encode("utf-8")) > app.settings.gateway_max_message_bytes:
        raise ValueError("Gateway frame is too large")
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Gateway frame must be valid JSON") from exc
    if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
        raise ValueError("Gateway frame must be a JSON-RPC 2.0 object")

    # Responses to upstream server→client requests are allowed only for request ids actually observed.
    if "method" not in frame:
        request_id = str(frame.get("id", ""))
        if request_id not in open_requests:
            raise ValueError("Unknown server request response id")
        open_requests.discard(request_id)
        return json.dumps(frame, separators=(",", ":"), ensure_ascii=False)

    method = str(frame.get("method") or "")
    if method not in app.settings.gateway_allowed_methods:
        return _rpc_error(frame.get("id"), -32601, f"Method is not allowed by Companion: {method}")
    params = frame.get("params")
    if params is None:
        params = {}
        frame["params"] = params
    if not isinstance(params, dict):
        return _rpc_error(frame.get("id"), -32602, "JSON-RPC params must be an object")

    if method not in {"ping", "gateway.capabilities", "client.capabilities"}:
        supplied = str(params.get("profile") or profile)
        if supplied != profile:
            return _rpc_error(frame.get("id"), 4031, "Cross-profile gateway request refused")
        params["profile"] = profile

    if method in {"command.dispatch", "command.resolve", "prompt.submit", "prompt.background"}:
        value = params.get("command") if method.startswith("command.") else params.get("text")
        command = str(value or "").strip().lower()
        if command.startswith(_BLOCKED_COMMAND_PREFIXES):
            return _rpc_error(frame.get("id"), 4032, "Administrative slash command refused by Companion")

    if method == "session.create":
        # A remote client may not choose an arbitrary server working directory.
        params.pop("cwd", None)

    if method in _RAW_ATTACHMENT_METHODS:
        return _rpc_error(
            frame.get("id"), 4033,
            "Raw or drop-detected attachments are disabled; upload through Companion first",
        )

    if method in _ATTACHMENT_METHODS:
        if any(params.get(key) for key in ("content_base64", "data", "data_url")):
            return _rpc_error(
                frame.get("id"), 4033,
                "Inline attachment data is disabled; upload through Companion first",
            )
        if not params.get("path"):
            return _rpc_error(frame.get("id"), 4033, "An approved Companion upload path is required")
        requested = str(Path(str(params["path"])).resolve())
        upload = app.db.find_upload_by_path(user["id"], profile, requested)
        if not upload or not Path(requested).is_file():
            return _rpc_error(frame.get("id"), 4033, "Attachment path is not an approved Companion upload")
        params["path"] = requested

    return json.dumps(frame, separators=(",", ":"), ensure_ascii=False)


@router.post("/{profile}/ticket")
def create_ticket(
    request: Request, profile: str, user: dict = Depends(current_user)
) -> dict:
    app = state(request)
    spec = get_profile(request, profile, user=user, permission="gateway_live")
    if not app.settings.gateway_available:
        raise HTTPException(status_code=503, detail="The optional Hermes live gateway is not configured")
    token = new_token(32)
    expires = app.db.create_gateway_ticket(
        token=token, user_id=user["id"], profile=spec.slug,
        ttl_seconds=app.settings.gateway_ticket_seconds,
    )
    app.db.audit(
        event="gateway.ticket_created", user_id=user["id"], profile=spec.slug,
        metadata={"expires_at": expires}, ip=client_ip(request),
    )
    return {
        "ticket": token,
        "expires_at": expires,
        "path": f"/api/gateway/ws?ticket={token}",
        "profile": spec.slug,
        "allowed_methods": list(app.settings.gateway_allowed_methods),
    }


@router.websocket("/ws")
async def gateway_ws(websocket: WebSocket) -> None:
    app = state(websocket)
    ticket_value = websocket.query_params.get("ticket", "")
    ticket = app.db.consume_gateway_ticket(ticket_value) if ticket_value else None
    if not ticket:
        await websocket.close(code=4401, reason="Invalid or expired gateway ticket")
        return
    user = app.db.get_user(ticket["user_id"])
    if not user or not user.get("active") or not app.db.user_profile_allowed(user, ticket["profile"]):
        await websocket.close(code=4403, reason="Gateway access refused")
        return
    try:
        spec = app.settings.profile(ticket["profile"])
    except KeyError:
        await websocket.close(code=4404, reason="Profile unavailable")
        return
    if not spec.permissions.gateway_live or not app.settings.gateway_available:
        await websocket.close(code=4403, reason="Live gateway is disabled")
        return

    await websocket.accept()
    open_server_requests: set[str] = set()
    client_host = websocket.client.host if websocket.client else ""
    app.db.audit(
        event="gateway.connected", user_id=user["id"], profile=spec.slug,
        metadata={"client": client_host}, ip=client_host,
    )

    try:
        upstream_url = _upstream_ws_url(
            app.settings.hermes_serve_url, app.settings.hermes_serve_session_token
        )
        async with connect(
            upstream_url,
            additional_headers={"X-Hermes-Session-Token": app.settings.hermes_serve_session_token},
            open_timeout=app.settings.gateway_connect_timeout_seconds,
            max_size=app.settings.gateway_max_message_bytes,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        sanitized = _validate_client_frame(
                            app, user, spec.slug, raw, open_server_requests
                        )
                    except ValueError as exc:
                        await websocket.send_text(_rpc_error(None, -32600, str(exc)))
                        continue
                    if sanitized is not None:
                        # Policy errors are encoded as JSON-RPC responses and must stay client-side.
                        parsed = json.loads(sanitized)
                        if "error" in parsed and "method" not in parsed:
                            await websocket.send_text(sanitized)
                        else:
                            await upstream.send(sanitized)

            async def upstream_to_client() -> None:
                async for raw in upstream:
                    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                    if len(text.encode("utf-8")) > app.settings.gateway_max_message_bytes:
                        raise RuntimeError("Upstream gateway frame exceeded the configured limit")
                    try:
                        frame = json.loads(text)
                        if isinstance(frame, dict) and frame.get("method") not in {None, "event"} and "id" in frame:
                            open_server_requests.add(str(frame["id"]))
                    except json.JSONDecodeError:
                        pass
                    await websocket.send_text(text)

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except (WebSocketDisconnect, ConnectionClosed, asyncio.CancelledError):
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({
                "jsonrpc": "2.0", "method": "event",
                "params": {"type": "companion.gateway_error", "payload": {"error": type(exc).__name__}},
            }))
        except Exception:
            pass
    finally:
        app.db.audit(
            event="gateway.disconnected", user_id=user["id"], profile=spec.slug,
            metadata={"client": client_host}, ip=client_host,
        )
        try:
            await websocket.close()
        except Exception:
            pass
