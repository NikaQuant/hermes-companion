from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import require_admin, state


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    request: Request, limit: int = 100, event: str | None = None,
    profile: str | None = None, _admin: dict = Depends(require_admin),
) -> dict:
    return {
        "events": state(request).db.list_audit(limit, event=event, profile=profile)
    }
