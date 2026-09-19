from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import ProfileSpec, Settings
from .db import Database


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AppState:
    settings: Settings
    db: Database
    hermes: object


def state(request: Request | WebSocket) -> AppState:
    return request.app.state.companion


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    app_state = state(request)
    user = app_state.db.resolve_token(credentials.credentials, "access")
    if not user or not user.get("active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user


def client_ip(request: Request) -> str:
    if state(request).settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:100]
    return (request.client.host if request.client else "")[:100]


def get_profile(
    request: Request | WebSocket,
    profile: str,
    *,
    user: dict | None = None,
    permission: str = "read",
) -> ProfileSpec:
    try:
        spec = state(request).settings.profile(profile)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    if user is not None and not state(request).db.user_profile_allowed(user, spec.slug):
        raise HTTPException(status_code=404, detail="Profile is not exposed to this user")
    if not getattr(spec.permissions, permission, False):
        raise HTTPException(status_code=403, detail=f"Profile does not permit {permission}")
    return spec
