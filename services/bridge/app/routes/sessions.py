from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Request

from ..dependencies import client_ip, current_user, get_profile, state
from ..hermes.client import HermesUpstreamError, upstream_http_exception
from ..security import stable_session_key


router = APIRouter(prefix="/api/profiles/{profile}/sessions", tags=["sessions"])


def _session_key(request: Request, user: dict, profile: str) -> str:
    return stable_session_key(state(request).settings.app_secret, user["id"], profile)


async def _call(request: Request, spec, user, method: str, path: str, *, body=None, query=None):
    try:
        return await state(request).hermes.request(
            spec,
            method,
            path,
            query=query,
            json_body=body,
            session_key=_session_key(request, user, spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc


@router.get("")
async def list_sessions(request: Request, profile: str, user: dict = Depends(current_user)):
    spec = get_profile(request, profile, user=user)
    return await _call(request, spec, user, "GET", "/api/sessions", query=dict(request.query_params))


@router.post("")
async def create_session(
    request: Request,
    profile: str,
    body: dict[str, Any] = Body(default_factory=dict),
    user: dict = Depends(current_user),
):
    spec = get_profile(request, profile, user=user, permission="session_write")
    result = await _call(request, spec, user, "POST", "/api/sessions", body=body)
    state(request).db.audit(
        event="session.create", user_id=user["id"], profile=spec.slug,
        metadata={"title": body.get("title")}, ip=client_ip(request)
    )
    return result


@router.get("/{session_id}/messages")
async def messages(
    request: Request, profile: str, session_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user)
    return await _call(
        request, spec, user, "GET", f"/api/sessions/{quote(session_id, safe='')}/messages",
        query=dict(request.query_params)
    )


@router.patch("/{session_id}")
async def update_session(
    request: Request,
    profile: str,
    session_id: str,
    body: dict[str, Any],
    user: dict = Depends(current_user),
):
    spec = get_profile(request, profile, user=user, permission="session_write")
    result = await _call(request, spec, user, "PATCH", f"/api/sessions/{quote(session_id, safe='')}", body=body)
    state(request).db.audit(
        event="session.update", user_id=user["id"], profile=spec.slug,
        metadata={"session_id": session_id, "fields": list(body)}, ip=client_ip(request)
    )
    return result


@router.delete("/{session_id}")
async def delete_session(
    request: Request, profile: str, session_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="session_write")
    result = await _call(request, spec, user, "DELETE", f"/api/sessions/{quote(session_id, safe='')}")
    state(request).db.audit(
        event="session.delete", user_id=user["id"], profile=spec.slug,
        metadata={"session_id": session_id}, ip=client_ip(request)
    )
    return result


@router.post("/{session_id}/fork")
async def fork_session(
    request: Request,
    profile: str,
    session_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    user: dict = Depends(current_user),
):
    spec = get_profile(request, profile, user=user, permission="session_write")
    result = await _call(
        request, spec, user, "POST", f"/api/sessions/{quote(session_id, safe='')}/fork", body=body
    )
    state(request).db.audit(
        event="session.fork", user_id=user["id"], profile=spec.slug,
        metadata={"session_id": session_id}, ip=client_ip(request)
    )
    return result
