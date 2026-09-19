from __future__ import annotations

import asyncio
import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..dependencies import client_ip, current_user, get_profile, state
from ..hermes.client import HermesUpstreamError, upstream_http_exception
from .. import push
from ..schemas import ApprovalRequest, RunCreate, SteerRequest
from ..security import stable_session_key
from ..sse import SSEObserver


router = APIRouter(prefix="/api/profiles/{profile}/runs", tags=["runs"])


def _notify(app, **kwargs) -> None:
    """Store a notification and fan it out to push subscriptions (best effort)."""
    notification = app.db.create_notification(**kwargs)
    try:
        asyncio.create_task(push.broadcast(app, notification))
    except RuntimeError:  # no running loop (offline tooling/tests): inbox only
        pass


def _session_key(request: Request, user: dict, profile: str) -> str:
    return stable_session_key(state(request).settings.app_secret, user["id"], profile)


@router.post("")
async def start_run(
    request: Request, profile: str, body: RunCreate, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="chat")
    payload = body.model_dump(exclude_none=True)
    requested_key = payload.pop("idempotency_key", None)
    key = request.headers.get("idempotency-key") or requested_key or str(uuid.uuid4())
    try:
        result = await state(request).hermes.request(
            spec,
            "POST",
            "/v1/runs",
            json_body=payload,
            session_key=_session_key(request, user, spec.slug),
            extra_headers={"Idempotency-Key": key},
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc
    state(request).db.audit(
        event="run.start", user_id=user["id"], profile=spec.slug,
        metadata={
            "session_id": payload.get("session_id"),
            "model": payload.get("model"),
            "idempotency_key": key,
        },
        ip=client_ip(request),
    )
    if isinstance(result, dict):
        result.setdefault("idempotency_key", key)
    return result


@router.get("/{run_id}")
async def run_status(
    request: Request, profile: str, run_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user)
    try:
        return await state(request).hermes.request(
            spec,
            "GET",
            f"/v1/runs/{quote(run_id, safe='')}",
            session_key=_session_key(request, user, spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc


@router.get("/{run_id}/events")
async def run_events(
    request: Request, profile: str, run_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user)

    app = state(request)

    def observe(event_name: str, payload: dict) -> None:
        title = message = severity = kind = None
        if event_name in {"approval.request", "run.waiting_for_approval"}:
            title, message, severity, kind = (
                "Hermes approval required",
                str(payload.get("description") or payload.get("command") or "A run is waiting for your decision."),
                "warning",
                "approval",
            )
        elif event_name == "run.completed":
            title, message, severity, kind = (
                "Hermes run completed", "The requested work finished successfully.", "success", "run.completed"
            )
        elif event_name in {"run.failed", "run.interrupted", "run.cancelled"}:
            title, message, severity, kind = (
                "Hermes run did not complete",
                str(payload.get("error") or payload.get("turn_exit_reason") or event_name),
                "error" if event_name == "run.failed" else "warning",
                event_name,
            )
        if title:
            _notify(
                app,
                user_id=user["id"], profile=spec.slug, kind=kind, title=title,
                message=message[:2000], severity=severity,
                metadata={"run_id": run_id, "event": event_name, "session_id": payload.get("session_id")},
                dedupe_key=f"run:{spec.slug}:{run_id}:{event_name}",
            )

    async def generate():
        observer = SSEObserver(observe)
        try:
            async with asyncio.timeout(app.settings.hermes_sse_max_seconds):
                async for chunk in app.hermes.stream(
                    spec,
                    "GET",
                    f"/v1/runs/{quote(run_id, safe='')}/events",
                    session_key=_session_key(request, user, spec.slug),
                    extra_headers={"Last-Event-ID": request.headers.get("last-event-id", "")},
                ):
                    observer.feed(chunk)
                    yield chunk
        except TimeoutError:
            payload = {"event": "bridge.timeout", "detail": "Stream reached the bridge time limit"}
            _notify(
                app,
                user_id=user["id"], profile=spec.slug, kind="bridge.timeout",
                title="Hermes stream timed out", message=payload["detail"], severity="warning",
                metadata={"run_id": run_id}, dedupe_key=f"run:{spec.slug}:{run_id}:bridge.timeout",
            )
            yield f"event: bridge.timeout\ndata: {json.dumps(payload)}\n\n".encode()
        except HermesUpstreamError as exc:
            # Once streaming starts HTTP status cannot be changed; emit a standards-compatible error event.
            payload = {
                "event": "bridge.error",
                "status": exc.status_code,
                "detail": "Upstream stream failed",
            }
            _notify(
                app,
                user_id=user["id"], profile=spec.slug, kind="bridge.error",
                title="Hermes stream failed", message=payload["detail"], severity="error",
                metadata={"run_id": run_id, "status": exc.status_code},
                dedupe_key=f"run:{spec.slug}:{run_id}:bridge.error",
            )
            yield f"event: bridge.error\ndata: {json.dumps(payload)}\n\n".encode()
        finally:
            observer.flush()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{run_id}/approval")
async def approve_run(
    request: Request,
    profile: str,
    run_id: str,
    body: ApprovalRequest,
    user: dict = Depends(current_user),
):
    spec = get_profile(request, profile, user=user, permission="approval")
    if not state(request).settings.allow_wide_approvals and body.choice not in {"once", "deny"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Mobile approvals are restricted to once or deny")
    payload = {"choice": body.choice, "resolve_all": body.resolve_all}
    try:
        result = await state(request).hermes.request(
            spec,
            "POST",
            f"/v1/runs/{quote(run_id, safe='')}/approval",
            json_body=payload,
            session_key=_session_key(request, user, spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc
    state(request).db.audit(
        event="run.approval", user_id=user["id"], profile=spec.slug,
        metadata={"run_id": run_id, "choice": body.choice, "resolve_all": body.resolve_all},
        ip=client_ip(request),
    )
    return result


@router.post("/{run_id}/steer")
async def steer_run(
    request: Request,
    profile: str,
    run_id: str,
    body: SteerRequest,
    user: dict = Depends(current_user),
):
    spec = get_profile(request, profile, user=user, permission="run_control")
    try:
        result = await state(request).hermes.request(
            spec,
            "POST",
            f"/v1/runs/{quote(run_id, safe='')}/steer",
            json_body={"prompt": body.input},
            session_key=_session_key(request, user, spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc
    state(request).db.audit(
        event="run.steer", user_id=user["id"], profile=spec.slug,
        metadata={"run_id": run_id, "characters": len(body.input)}, ip=client_ip(request)
    )
    return result


@router.post("/{run_id}/stop")
async def stop_run(
    request: Request, profile: str, run_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="run_control")
    try:
        result = await state(request).hermes.request(
            spec,
            "POST",
            f"/v1/runs/{quote(run_id, safe='')}/stop",
            json_body={},
            session_key=_session_key(request, user, spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc
    state(request).db.audit(
        event="run.stop", user_id=user["id"], profile=spec.slug,
        metadata={"run_id": run_id}, ip=client_ip(request)
    )
    return result
