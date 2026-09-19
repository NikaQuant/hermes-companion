from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import push as push_service
from ..dependencies import client_ip, current_user, state

router = APIRouter(prefix="/api/push", tags=["push"])


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushEndpointRequest(BaseModel):
    endpoint: str


@router.get("/key")
def push_key(request: Request, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    if not push_service.push_enabled(app.settings):
        raise HTTPException(status_code=503, detail="Push notifications are not configured on this bridge")
    return {"public_key": app.settings.vapid_public_key}


@router.get("/subscriptions")
def list_subscriptions(request: Request, user: dict = Depends(current_user)) -> dict:
    subscriptions = state(request).db.list_push_subscriptions(user["id"])
    return {
        "subscriptions": [
            {
                "id": item["id"],
                "created_at": item["created_at"],
                "last_used_at": item["last_used_at"],
                "user_agent": item["user_agent"],
            }
            for item in subscriptions
        ]
    }


@router.post("/subscribe")
def subscribe(request: Request, body: PushSubscribeRequest, user: dict = Depends(current_user)) -> dict:
    if not body.endpoint.startswith("https://"):
        raise HTTPException(status_code=422, detail="A browser push endpoint is required")
    if len(body.p256dh) < 16 or len(body.auth) < 4:
        raise HTTPException(status_code=422, detail="Incomplete subscription keys")
    app = state(request)
    record = app.db.add_push_subscription(
        user_id=user["id"],
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=request.headers.get("user-agent", ""),
    )
    app.db.audit(
        event="push.subscribed", user_id=user["id"], ip=client_ip(request),
        metadata={"subscription_id": record.get("id")},
    )
    return {"id": record.get("id")}


@router.delete("/subscribe")
def unsubscribe_by_endpoint(request: Request, body: PushEndpointRequest, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    record = app.db.get_push_subscription_by_endpoint(body.endpoint)
    if not record or record.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    app.db.drop_push_endpoint(body.endpoint)
    app.db.audit(
        event="push.unsubscribed", user_id=user["id"], ip=client_ip(request),
        metadata={"subscription_id": record.get("id")},
    )
    return {"ok": True}


@router.delete("/subscriptions/{subscription_id}")
def unsubscribe(request: Request, subscription_id: str, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    if not app.db.delete_push_subscription(user["id"], subscription_id):
        raise HTTPException(status_code=404, detail="Subscription not found")
    app.db.audit(
        event="push.unsubscribed", user_id=user["id"], ip=client_ip(request),
        metadata={"subscription_id": subscription_id},
    )
    return {"ok": True}
