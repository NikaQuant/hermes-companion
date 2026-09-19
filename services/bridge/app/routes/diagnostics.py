from __future__ import annotations

import asyncio
import shutil
import time
from fastapi import APIRouter, Depends, Request

from ..dependencies import get_profile, require_admin, state
from ..hermes.client import HermesUpstreamError
from ..security import stable_session_key
from ..version import __version__


router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
def diagnostics(request: Request, admin: dict = Depends(require_admin)) -> dict:
    app = state(request)
    disk = shutil.disk_usage(app.settings.project_root)
    return {
        "version": __version__,
        "environment": app.settings.app_env,
        "database": app.db.stats(),
        "paths": {
            "project_root": str(app.settings.project_root),
            "web_dist": str(app.settings.web_dist_dir),
            "upload_root": str(app.settings.upload_root),
            "backup_root": str(app.settings.backup_root),
        },
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "web": {
            "dist_exists": app.settings.web_dist_dir.is_dir(),
            "index_exists": (app.settings.web_dist_dir / "index.html").is_file(),
        },
        "security": {
            "trust_proxy_headers": app.settings.trust_proxy_headers,
            "allow_wide_approvals": app.settings.allow_wide_approvals,
            "max_request_body_bytes": app.settings.max_request_body_bytes,
            "max_upload_bytes": app.settings.max_upload_bytes,
            "upload_scanner_configured": bool(app.settings.upload_scan_command),
            "gateway_available": app.settings.gateway_available,
            "gateway_allowed_method_count": len(app.settings.gateway_allowed_methods),
        },
        "profiles": [
            profile.public_dict(gateway_available=app.settings.gateway_available)
            for profile in app.settings.profiles
        ],
        "operator": {"id": admin["id"], "email": admin["email"]},
    }


@router.post("/profiles/{profile}/probe")
async def probe_profile(
    request: Request, profile: str, admin: dict = Depends(require_admin)
) -> dict:
    app = state(request)
    spec = get_profile(request, profile, user=admin)
    session_key = stable_session_key(app.settings.app_secret, admin["id"], spec.slug)

    async def call(name: str, path: str):
        started = time.perf_counter()
        try:
            payload = await app.hermes.request(spec, "GET", path, session_key=session_key)
            return {
                "name": name, "ok": True,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "payload": payload,
            }
        except HermesUpstreamError as exc:
            return {
                "name": name, "ok": False, "status": exc.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": "Hermes endpoint returned an error",
            }
        except Exception as exc:
            return {
                "name": name, "ok": False,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": type(exc).__name__,
            }

    checks = await asyncio.gather(
        call("health", "/health"),
        call("capabilities", "/v1/capabilities"),
        call("models", "/api/model/options"),
    )
    return {"profile": spec.public_dict(gateway_available=app.settings.gateway_available), "checks": checks}
