from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import Database
from .dependencies import AppState
from .hermes.client import HermesGateway
from .routes import (
    admin,
    audit,
    auth,
    backups,
    diagnostics,
    files,
    gateway,
    handoff,
    jobs,
    models,
    notifications,
    profiles,
    projects,
    prompts,
    push,
    runs,
    session_meta,
    sessions,
    webauthn,
)
from .security import utc_timestamp
from .version import __version__


logger = logging.getLogger("hermes_companion")


def _clean_expired_uploads(settings: Settings, database: Database) -> int:
    cutoff = utc_timestamp() - settings.upload_retention_days * 86400
    removed = 0
    for item in database.expired_uploads(cutoff):
        try:
            path = Path(item["path"]).resolve()
            path.relative_to(settings.upload_root.resolve())
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass
        except (OSError, ValueError):
            continue
        database.delete_upload(item["user_id"], item["id"])
        removed += 1
    return removed


def create_app(
    settings: Settings | None = None,
    *,
    hermes_factory: Callable[[Settings], HermesGateway] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    settings.backup_root.mkdir(parents=True, exist_ok=True)
    database = Database(settings.database_path)
    database.bootstrap_admin(settings.initial_admin_email, settings.initial_admin_password)
    database.cleanup(notification_retention_days=settings.notification_retention_days)
    _clean_expired_uploads(settings, database)
    hermes = (hermes_factory or HermesGateway)(settings)

    app = FastAPI(
        title="Hermes Companion Bridge",
        description="Authenticated multi-profile control plane for a regular Hermes installation.",
        version=__version__,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
    )
    app.state.companion = AppState(settings=settings, db=database, hermes=hermes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        started = time.perf_counter()
        content_length = request.headers.get("content-length")
        if content_length and request.url.path.startswith("/api/"):
            try:
                maximum = settings.max_request_body_bytes
                if request.url.path == "/api/files" and request.method == "POST":
                    # Multipart framing adds a small amount above the content itself.
                    maximum = max(maximum, settings.max_upload_bytes + 1024 * 1024)
                if int(content_length) > maximum:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' https: http: ws: wss:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        forwarded_proto = request.headers.get("x-forwarded-proto", "") if settings.trust_proxy_headers else ""
        if request.url.scheme == "https" or forwarded_proto.lower() == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter()-started)*1000:.1f}"
        return response

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        logger.exception("Unhandled bridge error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal bridge error"})

    @app.get("/api/health", tags=["health"])
    async def bridge_health() -> dict:
        return {
            "status": "ok",
            "service": "hermes-companion-bridge",
            "version": __version__,
            "environment": settings.app_env,
            "live_gateway": settings.gateway_available,
        }

    for router in (
        auth.router,
        profiles.router,
        projects.router,
        models.router,
        sessions.router,
        session_meta.router,
        runs.router,
        jobs.router,
        files.router,
        prompts.router,
        notifications.router,
        handoff.router,
        push.router,
        webauthn.router,
        gateway.router,
        admin.router,
        diagnostics.router,
        backups.router,
        audit.router,
    ):
        app.include_router(router)

    dist = settings.web_dist_dir
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    if dist.is_dir() and (dist / "index.html").exists():
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            requested = (dist / full_path).resolve()
            try:
                requested.relative_to(dist.resolve())
            except ValueError:
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            if requested.is_file():
                return FileResponse(requested)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
