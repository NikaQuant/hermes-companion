from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import is_hard_blocked_profile, normalize_profile_slug
from ..dependencies import client_ip, require_admin, state
from ..schemas import AdminPasswordResetRequest, UserCreateRequest, UserUpdateRequest


router = APIRouter(prefix="/api/admin", tags=["administration"])


def _validated_profiles(request: Request, profiles: list[str]) -> list[str]:
    result: list[str] = []
    for raw in profiles:
        slug = normalize_profile_slug(raw)
        if is_hard_blocked_profile(slug):
            raise HTTPException(status_code=400, detail=f"Forbidden profile: {raw}")
        try:
            state(request).settings.profile(slug, require_configured=False)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown profile: {raw}") from exc
        if slug not in result:
            result.append(slug)
    return result


def _public(user: dict) -> dict:
    return {key: value for key, value in user.items() if key != "password_hash"}


@router.get("/users")
def list_users(request: Request, _admin: dict = Depends(require_admin)) -> dict:
    return {"users": [_public(user) for user in state(request).db.list_users()]}


@router.post("/users")
def create_user(
    request: Request, body: UserCreateRequest, admin: dict = Depends(require_admin)
) -> dict:
    profiles = _validated_profiles(request, body.profiles)
    try:
        user = state(request).db.create_user(
            email=body.email.lower(), password=body.password, role=body.role,
            active=body.active, profiles=profiles,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A user with that email already exists") from exc
    user["profiles"] = profiles
    state(request).db.audit(
        event="admin.user_created", user_id=admin["id"], ip=client_ip(request),
        metadata={"target_user": user["id"], "email": user["email"], "role": body.role, "profiles": profiles},
    )
    return _public(user)


@router.patch("/users/{user_id}")
def update_user(
    request: Request, user_id: str, body: UserUpdateRequest, admin: dict = Depends(require_admin)
) -> dict:
    if user_id == admin["id"] and (body.active is False or body.role == "user"):
        raise HTTPException(status_code=400, detail="You cannot disable or demote your own active administrator")
    profiles = _validated_profiles(request, body.profiles) if body.profiles is not None else None
    user = state(request).db.update_user(
        user_id, role=body.role, active=body.active, profiles=profiles
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    state(request).db.audit(
        event="admin.user_updated", user_id=admin["id"], ip=client_ip(request),
        metadata={
            "target_user": user_id, "role": body.role, "active": body.active,
            "profiles": profiles,
        },
    )
    return _public(user)


@router.post("/users/{user_id}/password")
def reset_password(
    request: Request, user_id: str, body: AdminPasswordResetRequest,
    admin: dict = Depends(require_admin),
) -> dict:
    if not state(request).db.set_password(user_id, body.password, revoke_tokens=True):
        raise HTTPException(status_code=404, detail="User not found")
    state(request).db.audit(
        event="admin.password_reset", user_id=admin["id"], ip=client_ip(request),
        metadata={"target_user": user_id},
    )
    return {"ok": True, "sessions_revoked": True}


@router.delete("/users/{user_id}")
def delete_user(request: Request, user_id: str, admin: dict = Depends(require_admin)) -> dict:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own administrator account")
    target = state(request).db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "admin":
        active_admins = [u for u in state(request).db.list_users() if u["role"] == "admin" and u["active"]]
        if len(active_admins) <= 1:
            raise HTTPException(status_code=400, detail="The final active administrator cannot be deleted")
    state(request).db.delete_user(user_id)
    state(request).db.audit(
        event="admin.user_deleted", user_id=admin["id"], ip=client_ip(request),
        metadata={"target_user": user_id, "email": target["email"]},
    )
    return {"ok": True}
