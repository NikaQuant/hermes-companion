from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import current_user, state
from ..schemas import NotificationReadRequest


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    request: Request, unread_only: bool = False, limit: int = 100,
    user: dict = Depends(current_user),
) -> dict:
    return {
        "notifications": state(request).db.list_notifications(
            user["id"], limit=limit, unread_only=unread_only
        ),
        "unread": state(request).db.unread_notification_count(user["id"]),
    }


@router.patch("/{notification_id}")
def update_notification(
    request: Request, notification_id: str, body: NotificationReadRequest,
    user: dict = Depends(current_user),
) -> dict:
    if not state(request).db.mark_notification_read(user["id"], notification_id, body.read):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/read-all")
def read_all(request: Request, user: dict = Depends(current_user)) -> dict:
    return {"ok": True, "updated": state(request).db.mark_all_notifications_read(user["id"])}


@router.delete("/{notification_id}")
def delete_notification(
    request: Request, notification_id: str, user: dict = Depends(current_user)
) -> dict:
    if not state(request).db.delete_notification(user["id"], notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}
