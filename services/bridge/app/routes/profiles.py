from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request

from ..dependencies import current_user, get_profile, state
from ..hermes.client import HermesUpstreamError, upstream_http_exception


router = APIRouter(prefix="/api", tags=["profiles"])


def _visible_profiles(request: Request, user: dict):
    app = state(request)
    return [
        profile for profile in app.settings.profiles
        if app.db.user_profile_allowed(user, profile.slug)
    ]


@router.get("/profiles")
def list_profiles(request: Request, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    return {
        "profiles": [
            profile.public_dict(gateway_available=app.settings.gateway_available)
            for profile in _visible_profiles(request, user)
        ]
    }


@router.get("/profiles/{profile}/health")
async def profile_health(request: Request, profile: str, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    spec = get_profile(request, profile, user=user)
    try:
        health = await app.hermes.request(spec, "GET", "/health/detailed")
    except HermesUpstreamError as exc:
        if exc.status_code == 404:
            try:
                health = await app.hermes.request(spec, "GET", "/health")
            except HermesUpstreamError as nested:
                raise upstream_http_exception(nested) from nested
        else:
            raise upstream_http_exception(exc) from exc
    return {
        "profile": spec.public_dict(gateway_available=app.settings.gateway_available),
        "health": health,
    }


@router.get("/overview")
async def overview(request: Request, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    visible = _visible_profiles(request, user)
    configured = [profile for profile in visible if profile.configured]

    async def probe(spec):
        try:
            health = await app.hermes.request(spec, "GET", "/health")
            return {"profile": spec.slug, "online": True, "health": health}
        except Exception as exc:  # status overview must remain available when one profile is down
            return {"profile": spec.slug, "online": False, "error": str(exc)[:300]}

    statuses = await asyncio.gather(*(probe(profile) for profile in configured))
    return {
        "bridge": {
            "online": True,
            "environment": app.settings.app_env,
            "live_gateway": app.settings.gateway_available,
        },
        "profiles": [
            profile.public_dict(gateway_available=app.settings.gateway_available)
            for profile in visible
        ],
        "statuses": statuses,
        "unread_notifications": app.db.unread_notification_count(user["id"]),
        "attention": {
            "unread": app.db.unread_notification_count(user["id"]),
            "approvals": app.db.count_unread_notifications_of_kind(user["id"], "approval"),
        },
    }
