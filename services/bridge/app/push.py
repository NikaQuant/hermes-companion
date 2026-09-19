"""Web Push (VAPID) fan-out for Companion notifications.

The notification inbox stays the source of truth; push is a best-effort delivery
channel on top. A subscription that the push service reports gone (404/410) is
pruned automatically; every other failure is logged and the subscription kept.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from pywebpush import WebPushException, webpush

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .dependencies import AppState

logger = logging.getLogger("hermes_companion")


def push_enabled(settings: Any) -> bool:
    return bool(settings.vapid_private_key and settings.vapid_public_key and settings.vapid_subject)


def _payload(notification: dict[str, Any], base_url: str) -> bytes:
    body = {
        "id": notification.get("id"),
        "title": notification.get("title") or "Hermes Companion",
        "body": str(notification.get("message") or "")[:300],
        "severity": notification.get("severity") or "info",
        "profile": notification.get("profile"),
        "kind": notification.get("kind"),
        "tag": f"hc-{notification.get('kind') or 'note'}",
        "url": (base_url or "").rstrip("/"),
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _deliver(settings: Any, subscription: dict[str, Any], data: bytes) -> bool:
    """Send one push. Returns False only when the subscription is permanently gone."""
    subscription_info = {
        "endpoint": subscription["endpoint"],
        "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=3600,
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            return False
        logger.warning("push delivery failed (status=%s): %s", status, str(exc)[:200])
        return True
    except Exception as exc:  # noqa: BLE001 - network/DNS errors must never break a run stream
        logger.warning("push delivery error: %s", str(exc)[:200])
        return True


async def broadcast(app: "AppState", notification: dict[str, Any]) -> None:
    """Deliver a stored notification row to the user's push subscriptions."""
    if not push_enabled(app.settings):
        return
    user_id = notification.get("user_id")
    if not user_id:
        return
    subscriptions = app.db.list_push_subscriptions(user_id)
    if not subscriptions:
        return
    data = _payload(notification, app.settings.public_app_url)
    settings = app.settings
    db = app.db

    def _run() -> None:
        for subscription in subscriptions:
            if _deliver(settings, subscription, data):
                db.touch_push_endpoint(subscription["endpoint"])
            else:
                db.drop_push_endpoint(subscription["endpoint"])

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # no loop (offline tooling/tests): inbox only
        return
    await loop.run_in_executor(None, _run)
