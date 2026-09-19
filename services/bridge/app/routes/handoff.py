from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import current_user, get_profile, state
from ..schemas import HandoffCreate
from ..security import new_token


router = APIRouter(prefix="/api/handoff", tags=["handoff"])


@router.post("")
def create_handoff(request: Request, body: HandoffCreate, user: dict = Depends(current_user)) -> dict:
    spec = get_profile(request, body.profile, user=user, permission="read")
    token = new_token(24)
    expires = state(request).db.create_handoff(
        token=token,
        user_id=user["id"],
        profile=spec.slug,
        session_id=body.session_id,
        ttl_seconds=300,
    )
    base = state(request).settings.public_app_url
    query = urlencode({"handoff": token})
    return {"token": token, "expires_at": expires, "url": f"{base}/?{query}" if base else f"/?{query}"}


@router.get("/{token}")
def consume_handoff(request: Request, token: str, user: dict = Depends(current_user)) -> dict:
    handoff = state(request).db.consume_handoff(token=token, user_id=user["id"])
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff is invalid, expired, or already used")
    return {"profile": handoff["profile"], "session_id": handoff["session_id"]}
