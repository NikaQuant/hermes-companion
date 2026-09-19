from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_TRUE = {"1", "true", "yes", "on"}
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_HARD_BLOCKED = {
    "live-safe",
    "live_safe",
    "livesafe",
    "live-judge",
    "live_judge",
    "livejudge",
    "hermes-safety",
    "hermes_safety",
    "hermessafety",
    "safety-world",
    "safety_world",
    "safetyworld",
}
_DEFAULT_UPLOAD_EXTENSIONS = (
    ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".css", ".sql",
    ".xml", ".log", ".ini", ".cfg", ".mq5", ".mqh", ".set", ".pdf", ".png", ".jpg",
    ".jpeg", ".webp", ".gif",
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value



def _webauthn_rp_id(explicit: str, public_app_url: str) -> str:
    """RP ID for passkeys: explicit override, else the host of the public HTTPS URL.

    An RP ID must be a registrable domain; bare hosts like 127.0.0.1 are useless for
    the tailnet/phone flow, so a URL without a dotted host disables the feature.
    """
    if explicit:
        return explicit
    try:
        from urllib.parse import urlparse

        host = (urlparse(public_app_url.strip()).hostname or "").lower()
    except ValueError:
        host = ""
    return host if "." in host else ""


def _split_command(value: str, *, windows: bool | None = None) -> tuple[str, ...]:
    if not value.strip():
        return ()
    use_windows = os.name == "nt" if windows is None else windows
    parts = shlex.split(value, posix=not use_windows)
    if use_windows:
        parts = [
            part[1:-1]
            if len(part) >= 2 and part[0] == part[-1] and part[0] in {"\"", "'"}
            else part
            for part in parts
        ]
    return tuple(parts)

def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def normalize_profile_slug(value: str) -> str:
    return value.strip().lower()


def is_hard_blocked_profile(value: str) -> bool:
    normalized = normalize_profile_slug(value)
    compact = normalized.replace("-", "").replace("_", "").replace(" ", "")
    return normalized in _HARD_BLOCKED or compact in {
        "livesafe",
        "livejudge",
        "hermessafety",
        "safetyworld",
    }


@dataclass(frozen=True)
class ProfilePermissions:
    read: bool = True
    chat: bool = False
    session_write: bool = False
    run_control: bool = False
    approval: bool = False
    jobs_write: bool = False
    files_write: bool = False
    gateway_live: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProfilePermissions":
        source = data or {}
        defaults = cls()
        return cls(**{
            name: bool(source.get(name, getattr(defaults, name)))
            for name in cls.__dataclass_fields__
        })

    def as_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class ProfileSpec:
    slug: str
    label: str
    description: str
    route_prefix: str
    api_key_env: str
    accent: str = "#8b5cf6"
    project_kind: str = "general"
    permissions: ProfilePermissions = field(default_factory=ProfilePermissions)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()

    @property
    def configured(self) -> bool:
        return len(self.api_key) >= 8

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileSpec":
        slug = normalize_profile_slug(str(data.get("slug", "")))
        if not _PROFILE_RE.fullmatch(slug):
            raise ValueError(f"Invalid Hermes profile slug: {slug!r}")
        if is_hard_blocked_profile(slug):
            raise ValueError(f"Safety World profile is forbidden: {slug}")
        route_prefix = str(data.get("route_prefix", "")).strip().rstrip("/")
        if route_prefix and route_prefix != f"/p/{slug}":
            raise ValueError(f"Route prefix for {slug} must be /p/{slug}")
        api_key_env = str(data.get("api_key_env") or "").strip()
        if not _ENV_KEY_RE.fullmatch(api_key_env):
            raise ValueError(f"Invalid API key environment variable for {slug}: {api_key_env!r}")
        accent = str(data.get("accent") or "#8b5cf6")
        if not _HEX_COLOR_RE.fullmatch(accent):
            accent = "#8b5cf6"
        return cls(
            slug=slug,
            label=str(data.get("label") or slug)[:120],
            description=str(data.get("description") or "")[:1000],
            route_prefix=route_prefix,
            api_key_env=api_key_env,
            accent=accent,
            project_kind=str(data.get("project_kind") or "general")[:64],
            permissions=ProfilePermissions.from_dict(data.get("permissions")),
        )

    def public_dict(self, *, gateway_available: bool = False) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "description": self.description,
            "accent": self.accent,
            "project_kind": self.project_kind,
            "configured": self.configured,
            "gateway_available": bool(gateway_available and self.permissions.gateway_live),
            "permissions": self.permissions.as_dict(),
        }


@dataclass(frozen=True)
class Settings:
    project_root: Path
    app_env: str
    app_secret: str
    database_path: Path
    access_token_minutes: int
    refresh_token_days: int
    cors_origins: tuple[str, ...]
    web_dist_dir: Path
    initial_admin_email: str
    initial_admin_password: str
    hermes_base_url: str
    hermes_profiles_file: Path
    hermes_request_timeout_seconds: float
    hermes_connect_timeout_seconds: float
    hermes_sse_max_seconds: float
    hermes_serve_url: str
    hermes_serve_session_token: str
    gateway_ticket_seconds: int
    gateway_connect_timeout_seconds: float
    gateway_max_message_bytes: int
    gateway_allowed_methods: tuple[str, ...]
    allow_wide_approvals: bool
    public_app_url: str
    trust_proxy_headers: bool
    max_request_body_bytes: int
    upload_root: Path
    max_upload_bytes: int
    upload_allowed_extensions: tuple[str, ...]
    upload_retention_days: int
    upload_scan_command: tuple[str, ...]
    upload_scan_timeout_seconds: float
    backup_root: Path
    notification_retention_days: int
    vapid_public_key: str
    vapid_private_key: str
    vapid_subject: str
    webauthn_rp_id: str
    profiles: tuple[ProfileSpec, ...]

    @property
    def gateway_available(self) -> bool:
        return bool(self.hermes_serve_url and len(self.hermes_serve_session_token) >= 16)

    @property
    def webauthn_available(self) -> bool:
        return bool(self.webauthn_rp_id)

    @classmethod
    def from_env(cls, *, project_root: Path | None = None, env_file: Path | None = None) -> "Settings":
        root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        _load_env_file(env_file or root / ".env")

        profiles_file = _resolve_path(
            os.getenv("HERMES_PROFILES_FILE", "./config/profiles.json"), root
        )
        payload = json.loads(profiles_file.read_text(encoding="utf-8"))
        specs = tuple(ProfileSpec.from_dict(item) for item in payload.get("profiles", []))
        if not specs:
            raise RuntimeError("No Hermes profiles are configured")
        if len({p.slug for p in specs}) != len(specs):
            raise RuntimeError("Duplicate Hermes profile slug")

        origins = _csv(os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,https://localhost,"
            "tauri://localhost,http://tauri.localhost,https://tauri.localhost",
        ))
        public_app = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
        if public_app:
            parsed = urlparse(public_app)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else public_app
            if origin and origin not in origins:
                origins = origins + (origin,)
        secret = os.getenv("APP_SECRET", "dev-only-change-this-secret")
        app_env = os.getenv("APP_ENV", "development").lower()
        if app_env == "production" and len(secret) < 32:
            raise RuntimeError("APP_SECRET must contain at least 32 characters in production")

        extensions = tuple(
            value if value.startswith(".") else f".{value}"
            for value in _csv(os.getenv("UPLOAD_ALLOWED_EXTENSIONS", ",".join(_DEFAULT_UPLOAD_EXTENSIONS)))
        )
        scan_command_raw = os.getenv("UPLOAD_SCAN_COMMAND", "").strip()
        try:
            scan_command = _split_command(scan_command_raw)
        except ValueError as exc:
            raise RuntimeError("UPLOAD_SCAN_COMMAND could not be parsed") from exc

        default_gateway_methods = (
            "ping", "gateway.capabilities", "client.capabilities", "commands.catalog", "model.options",
            "session.create", "session.list", "session.most_recent", "session.resume", "session.activate",
            "session.active_list", "session.close", "session.interrupt", "session.history", "session.compress",
            "session.branch", "session.title", "session.usage", "session.status", "session.events.since",
            "session.steer", "prompt.submit", "prompt.background", "command.resolve", "command.dispatch",
            "delegation.status", "subagent.interrupt", "subagent.steer", "spawn_tree.list", "spawn_tree.load",
            "spawn_tree.save", "clarify.lock", "image.attach", "pdf.attach", "file.attach",
            "image.detach",
        )

        return cls(
            project_root=root,
            app_env=app_env,
            app_secret=secret,
            database_path=_resolve_path(
                os.getenv("DATABASE_PATH", "./services/bridge/data/hermes_companion.db"), root
            ),
            access_token_minutes=max(5, int(os.getenv("ACCESS_TOKEN_MINUTES", "20"))),
            refresh_token_days=max(1, int(os.getenv("REFRESH_TOKEN_DAYS", "30"))),
            cors_origins=origins,
            web_dist_dir=_resolve_path(os.getenv("WEB_DIST_DIR", "./apps/web/dist"), root),
            initial_admin_email=os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower(),
            initial_admin_password=os.getenv("INITIAL_ADMIN_PASSWORD", ""),
            hermes_base_url=os.getenv("HERMES_BASE_URL", "http://127.0.0.1:8642").rstrip("/"),
            hermes_profiles_file=profiles_file,
            hermes_request_timeout_seconds=float(os.getenv("HERMES_REQUEST_TIMEOUT_SECONDS", "60")),
            hermes_connect_timeout_seconds=float(os.getenv("HERMES_CONNECT_TIMEOUT_SECONDS", "10")),
            hermes_sse_max_seconds=float(os.getenv("HERMES_SSE_MAX_SECONDS", "21600")),
            hermes_serve_url=os.getenv("HERMES_SERVE_URL", "").strip().rstrip("/"),
            hermes_serve_session_token=os.getenv("HERMES_SERVE_SESSION_TOKEN", "").strip(),
            gateway_ticket_seconds=max(15, min(300, int(os.getenv("GATEWAY_TICKET_SECONDS", "60")))),
            gateway_connect_timeout_seconds=max(2.0, float(os.getenv("GATEWAY_CONNECT_TIMEOUT_SECONDS", "10"))),
            gateway_max_message_bytes=max(65536, int(os.getenv("GATEWAY_MAX_MESSAGE_BYTES", "2097152"))),
            gateway_allowed_methods=_csv(os.getenv(
                "GATEWAY_ALLOWED_METHODS", ",".join(default_gateway_methods)
            )),
            allow_wide_approvals=os.getenv("ALLOW_WIDE_APPROVALS", "false").lower() in _TRUE,
            public_app_url=os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/"),
            trust_proxy_headers=os.getenv("TRUST_PROXY_HEADERS", "false").lower() in _TRUE,
            max_request_body_bytes=max(65536, int(os.getenv("MAX_REQUEST_BODY_BYTES", "2097152"))),
            upload_root=_resolve_path(os.getenv("UPLOAD_ROOT", "./services/bridge/data/uploads"), root),
            max_upload_bytes=max(65536, int(os.getenv("MAX_UPLOAD_BYTES", "26214400"))),
            upload_allowed_extensions=tuple(sorted(set(ext.lower() for ext in extensions))),
            upload_retention_days=max(1, int(os.getenv("UPLOAD_RETENTION_DAYS", "30"))),
            upload_scan_command=scan_command,
            upload_scan_timeout_seconds=max(1.0, float(os.getenv("UPLOAD_SCAN_TIMEOUT_SECONDS", "30"))),
            backup_root=_resolve_path(os.getenv("BACKUP_ROOT", "./backups"), root),
            notification_retention_days=max(1, int(os.getenv("NOTIFICATION_RETENTION_DAYS", "30"))),
            vapid_public_key=os.getenv("VAPID_PUBLIC_KEY", "").strip(),
            vapid_private_key=os.getenv("VAPID_PRIVATE_KEY", "").strip(),
            vapid_subject=(os.getenv("VAPID_SUBJECT", "") or "mailto:admin@hermescompanion.dev").strip(),
            webauthn_rp_id=_webauthn_rp_id(
                os.getenv("WEBAUTHN_RP_ID", "").strip(), os.getenv("PUBLIC_APP_URL", "")
            ),
            profiles=specs,
        )

    def profile(self, slug: str, *, require_configured: bool = True) -> ProfileSpec:
        normalized = normalize_profile_slug(slug)
        if is_hard_blocked_profile(normalized):
            raise KeyError("Profile is not exposed by this bridge")
        for profile in self.profiles:
            if profile.slug == normalized:
                if require_configured and not profile.configured:
                    raise KeyError("Profile is not configured")
                return profile
        raise KeyError("Unknown profile")
