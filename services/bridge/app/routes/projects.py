from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..dependencies import current_user, state
from ..hermes.client import HermesUpstreamError
from ..security import stable_session_key


router = APIRouter(prefix="/api/projects", tags=["projects"])


def _items(payload: Any, *keys: str) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


@router.get("")
async def projects(request: Request, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    profiles = [
        spec for spec in app.settings.profiles
        if spec.configured and app.db.user_profile_allowed(user, spec.slug)
    ]

    async def fetch(spec):
        session_key = stable_session_key(app.settings.app_secret, user["id"], spec.slug)

        async def call(path: str, query: dict | None = None):
            try:
                return await app.hermes.request(
                    spec, "GET", path, query=query, session_key=session_key
                )
            except HermesUpstreamError as exc:
                return {"_error": f"HTTP {exc.status_code}"}
            except Exception as exc:  # one project must not break the fleet page
                return {"_error": type(exc).__name__}

        health, sessions, jobs, capabilities = await asyncio.gather(
            call("/health"),
            call("/api/sessions", {"limit": 5}),
            call("/api/jobs"),
            call("/v1/capabilities"),
        )
        session_rows = _items(sessions, "sessions", "items")
        job_rows = _items(jobs, "jobs", "items")
        active_jobs = [
            job for job in job_rows
            if not (job.get("paused") is True or job.get("enabled") is False or job.get("status") == "paused")
        ]
        return {
            "profile": spec.public_dict(gateway_available=app.settings.gateway_available),
            "online": "_error" not in health,
            "health": None if "_error" in health else health,
            "error": health.get("_error") if isinstance(health, dict) else None,
            "sessions": session_rows[:5],
            "session_count_returned": len(session_rows),
            "jobs": job_rows[:5],
            "job_count": len(job_rows),
            "active_job_count": len(active_jobs),
            "capabilities": None if "_error" in capabilities else capabilities,
        }

    return {
        "projects": await asyncio.gather(*(fetch(spec) for spec in profiles)),
        "unread_notifications": app.db.unread_notification_count(user["id"]),
    }
