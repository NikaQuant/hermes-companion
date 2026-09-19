from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Request

from ..dependencies import client_ip, current_user, get_profile, state
from ..hermes.client import HermesUpstreamError, upstream_http_exception
from ..security import stable_session_key


router = APIRouter(prefix="/api/profiles/{profile}/jobs", tags=["automations"])


async def _call(request: Request, spec, user, method: str, path: str, *, body=None):
    try:
        return await state(request).hermes.request(
            spec,
            method,
            path,
            json_body=body,
            session_key=stable_session_key(state(request).settings.app_secret, user["id"], spec.slug),
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc


def _audit(request, user, spec, event, job_id=None, body=None):
    state(request).db.audit(
        event=event, user_id=user["id"], profile=spec.slug,
        metadata={"job_id": job_id, "fields": list(body or {})}, ip=client_ip(request)
    )


@router.get("")
async def list_jobs(request: Request, profile: str, user: dict = Depends(current_user)):
    spec = get_profile(request, profile, user=user)
    return await _call(request, spec, user, "GET", "/api/jobs")


@router.post("")
async def create_job(
    request: Request, profile: str, body: dict[str, Any], user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="jobs_write")
    result = await _call(request, spec, user, "POST", "/api/jobs", body=body)
    _audit(request, user, spec, "job.create", body=body)
    return result


@router.get("/{job_id}")
async def get_job(request: Request, profile: str, job_id: str, user: dict = Depends(current_user)):
    spec = get_profile(request, profile, user=user)
    return await _call(request, spec, user, "GET", f"/api/jobs/{quote(job_id, safe='')}")


@router.patch("/{job_id}")
async def update_job(
    request: Request, profile: str, job_id: str, body: dict[str, Any],
    user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="jobs_write")
    result = await _call(request, spec, user, "PATCH", f"/api/jobs/{quote(job_id, safe='')}", body=body)
    _audit(request, user, spec, "job.update", job_id, body)
    return result


@router.delete("/{job_id}")
async def delete_job(
    request: Request, profile: str, job_id: str, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user, permission="jobs_write")
    result = await _call(request, spec, user, "DELETE", f"/api/jobs/{quote(job_id, safe='')}")
    _audit(request, user, spec, "job.delete", job_id)
    return result


@router.post("/{job_id}/{action}")
async def job_action(
    request: Request, profile: str, job_id: str, action: str,
    body: dict[str, Any] = Body(default_factory=dict), user: dict = Depends(current_user)
):
    if action not in {"run", "pause", "resume"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Unknown job action")
    spec = get_profile(request, profile, user=user, permission="jobs_write")
    result = await _call(request, spec, user, "POST", f"/api/jobs/{quote(job_id, safe='')}/{action}", body=body)
    _audit(request, user, spec, f"job.{action}", job_id, body)
    return result
