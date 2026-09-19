from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import current_user, get_profile, state
from ..hermes.client import HermesUpstreamError, upstream_http_exception
from ..security import stable_session_key


router = APIRouter(prefix="/api/profiles/{profile}", tags=["models"])


@router.get("/model-options")
async def model_options(
    request: Request, profile: str, refresh: bool = False, user: dict = Depends(current_user)
):
    spec = get_profile(request, profile, user=user)
    session_key = stable_session_key(state(request).settings.app_secret, user["id"], spec.slug)
    try:
        return await state(request).hermes.request(
            spec,
            "GET",
            "/api/model/options",
            query={"refresh": "1" if refresh else None},
            session_key=session_key,
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc


@router.get("/capabilities")
async def capabilities(request: Request, profile: str, user: dict = Depends(current_user)):
    spec = get_profile(request, profile, user=user)
    session_key = stable_session_key(state(request).settings.app_secret, user["id"], spec.slug)
    try:
        return await state(request).hermes.request(
            spec, "GET", "/v1/capabilities", session_key=session_key
        )
    except HermesUpstreamError as exc:
        raise upstream_http_exception(exc) from exc
