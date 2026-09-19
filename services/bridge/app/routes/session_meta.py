from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import client_ip, current_user, get_profile, state
from ..schemas import SessionMetadataUpdate


router = APIRouter(prefix="/api/profiles/{profile}/session-metadata", tags=["session-metadata"])


@router.get("")
def list_metadata(request: Request, profile: str, user: dict = Depends(current_user)) -> dict:
    spec = get_profile(request, profile, user=user)
    return {"metadata": state(request).db.list_session_metadata(user["id"], spec.slug)}


@router.get("/{session_id}")
def get_metadata(
    request: Request, profile: str, session_id: str, user: dict = Depends(current_user)
) -> dict:
    spec = get_profile(request, profile, user=user)
    return state(request).db.get_session_metadata(user["id"], spec.slug, session_id)


@router.put("/{session_id}")
def update_metadata(
    request: Request, profile: str, session_id: str, body: SessionMetadataUpdate,
    user: dict = Depends(current_user),
) -> dict:
    spec = get_profile(request, profile, user=user)
    result = state(request).db.upsert_session_metadata(
        user_id=user["id"], profile=spec.slug, session_id=session_id,
        pinned=body.pinned, tags=body.tags, note=body.note,
    )
    state(request).db.audit(
        event="session.metadata_updated", user_id=user["id"], profile=spec.slug,
        metadata={"session_id": session_id, "pinned": body.pinned, "tags": body.tags},
        ip=client_ip(request),
    )
    return result
