from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import timedelta
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..dependencies import client_ip, current_user, state
from ..schemas import LoginRequest, LogoutRequest, PasswordChangeRequest, RefreshRequest
from ..security import new_token, verify_password


router = APIRouter(prefix="/api/auth", tags=["authentication"])
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempt_lock = asyncio.Lock()


async def _check_login_rate(key: str) -> None:
    now = monotonic()
    async with _attempt_lock:
        bucket = _attempts[key]
        while bucket and bucket[0] < now - 300:
            bucket.popleft()
        if len(bucket) >= 10:
            raise HTTPException(status_code=429, detail="Too many login attempts; retry later")
        bucket.append(now)


async def _clear_login_rate(key: str) -> None:
    async with _attempt_lock:
        _attempts.pop(key, None)


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "role": user["role"]}


def _issue_pair(
    request: Request, user: dict, device_name: str, device_id: str = ""
) -> dict:
    app = state(request)
    resolved_device_id = (device_id.strip() or new_token(18))[:120]
    access_token = new_token()
    refresh_token = new_token(48)
    access_expires = app.db.create_token(
        user_id=user["id"], kind="access", token=access_token,
        ttl=timedelta(minutes=app.settings.access_token_minutes),
        device_id=resolved_device_id, device_name=device_name,
    )
    refresh_expires = app.db.create_token(
        user_id=user["id"], kind="refresh", token=refresh_token,
        ttl=timedelta(days=app.settings.refresh_token_days),
        device_id=resolved_device_id, device_name=device_name,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "access_expires_at": access_expires,
        "refresh_expires_at": refresh_expires,
        "device_id": resolved_device_id,
        "user": _public_user(user),
    }


@router.post("/login")
async def login(request: Request, body: LoginRequest) -> dict:
    ip = client_ip(request)
    key = f"{ip}:{body.email.lower()}"
    await _check_login_rate(key)
    app = state(request)
    user = app.db.get_user_by_email(body.email.lower())
    valid = bool(user and user.get("active") and verify_password(body.password, user["password_hash"]))
    if not valid:
        app.db.audit(event="auth.login_failed", metadata={"email": body.email.lower()}, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    await _clear_login_rate(key)
    app.db.mark_login(user["id"])
    payload = _issue_pair(request, user, body.device_name, body.device_id)
    app.db.audit(
        event="auth.login", user_id=user["id"], ip=ip,
        metadata={"device": body.device_name, "device_id": payload["device_id"]},
    )
    return payload


@router.post("/refresh")
def refresh(request: Request, body: RefreshRequest) -> dict:
    app = state(request)
    access = new_token()
    refresh_token = new_token(48)
    rotated = app.db.rotate_refresh_token(
        old_token=body.refresh_token,
        new_access=access,
        new_refresh=refresh_token,
        access_ttl=timedelta(minutes=app.settings.access_token_minutes),
        refresh_ttl=timedelta(days=app.settings.refresh_token_days),
        device_id=body.device_id,
        device_name=body.device_name,
    )
    if not rotated:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user, access_expires, refresh_expires, device_id = rotated
    app.db.audit(
        event="auth.refresh", user_id=user["id"], ip=client_ip(request),
        metadata={"device_id": device_id},
    )
    return {
        "access_token": access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "access_expires_at": access_expires,
        "refresh_expires_at": refresh_expires,
        "device_id": device_id,
        "user": _public_user(user),
    }


@router.post("/logout")
def logout(request: Request, body: LogoutRequest, user: dict = Depends(current_user)) -> dict:
    credentials = request.headers.get("authorization", "").split(" ", 1)
    if len(credentials) == 2:
        state(request).db.revoke_token(credentials[1])
    if body.refresh_token:
        state(request).db.revoke_token(body.refresh_token)
    state(request).db.audit(event="auth.logout", user_id=user["id"], ip=client_ip(request))
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, user: dict = Depends(current_user)) -> dict:
    state(request).db.revoke_all_user_tokens(user["id"])
    state(request).db.audit(event="auth.logout_all", user_id=user["id"], ip=client_ip(request))
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    payload = _public_user(user)
    payload["device_id"] = user.get("device_id", "")
    return payload


@router.get("/devices")
def devices(request: Request, user: dict = Depends(current_user)) -> dict:
    rows = state(request).db.list_devices(user["id"])
    current = user.get("device_id", "")
    for row in rows:
        row["current"] = bool(current and row["device_id"] == current)
    return {"devices": rows}


@router.delete("/devices/{device_id}")
def revoke_device(request: Request, device_id: str, user: dict = Depends(current_user)) -> dict:
    revoked = state(request).db.revoke_device(user["id"], device_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Device not found")
    state(request).db.audit(
        event="auth.device_revoked", user_id=user["id"], ip=client_ip(request),
        metadata={"device_id": device_id, "current": device_id == user.get("device_id")},
    )
    return {"ok": True, "current_device": device_id == user.get("device_id")}


@router.post("/password")
def change_password(
    request: Request, body: PasswordChangeRequest, user: dict = Depends(current_user)
) -> dict:
    record = state(request).db.get_user(user["id"], include_hash=True)
    if not record or not verify_password(body.current_password, record["password_hash"]):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    state(request).db.set_password(user["id"], body.new_password, revoke_tokens=True)
    state(request).db.audit(event="auth.password_changed", user_id=user["id"], ip=client_ip(request))
    return {"ok": True, "reauthenticate": True}
