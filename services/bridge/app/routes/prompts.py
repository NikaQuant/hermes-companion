from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import client_ip, current_user, get_profile, state
from ..schemas import SavedPromptCreate, SavedPromptUpdate


router = APIRouter(prefix="/api/prompts", tags=["saved-prompts"])


def _profile(request: Request, user: dict, profile: str | None) -> str | None:
    if not profile:
        return None
    return get_profile(request, profile, user=user, permission="read").slug


@router.get("")
def list_prompts(request: Request, user: dict = Depends(current_user)) -> dict:
    prompts = state(request).db.list_prompts(user["id"])
    allowed = {
        spec.slug for spec in state(request).settings.profiles
        if state(request).db.user_profile_allowed(user, spec.slug)
    }
    return {"prompts": [item for item in prompts if not item.get("profile") or item["profile"] in allowed]}


@router.post("")
def create_prompt(
    request: Request, body: SavedPromptCreate, user: dict = Depends(current_user)
) -> dict:
    profile = _profile(request, user, body.profile)
    result = state(request).db.create_prompt(
        user_id=user["id"], title=body.title.strip(), prompt=body.prompt, profile=profile
    )
    state(request).db.audit(
        event="prompt.saved", user_id=user["id"], profile=profile, ip=client_ip(request),
        metadata={"prompt_id": result.get("id"), "title": body.title[:160]},
    )
    return result


@router.put("/{prompt_id}")
def update_prompt(
    request: Request, prompt_id: str, body: SavedPromptUpdate,
    user: dict = Depends(current_user),
) -> dict:
    profile = _profile(request, user, body.profile)
    result = state(request).db.update_prompt(
        user["id"], prompt_id, title=body.title.strip(), prompt=body.prompt, profile=profile
    )
    if not result:
        raise HTTPException(status_code=404, detail="Saved prompt not found")
    state(request).db.audit(
        event="prompt.updated", user_id=user["id"], profile=profile, ip=client_ip(request),
        metadata={"prompt_id": prompt_id},
    )
    return result


@router.delete("/{prompt_id}")
def delete_prompt(
    request: Request, prompt_id: str, user: dict = Depends(current_user)
) -> dict:
    if not state(request).db.delete_prompt(user["id"], prompt_id):
        raise HTTPException(status_code=404, detail="Saved prompt not found")
    state(request).db.audit(
        event="prompt.deleted", user_id=user["id"], ip=client_ip(request),
        metadata={"prompt_id": prompt_id},
    )
    return {"ok": True}
