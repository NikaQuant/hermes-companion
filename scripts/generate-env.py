from __future__ import annotations

import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path


def profile_env_names(root: Path) -> list[str]:
    """One API key per profile listed in config/profiles.json (default always included)."""
    names = ["HERMES_API_KEY_DEFAULT"]
    profiles_file = root / "config" / "profiles.json"
    if profiles_file.exists():
        try:
            for item in json.loads(profiles_file.read_text(encoding="utf-8")).get("profiles", []):
                env_name = str(item.get("api_key_env", "")).strip()
                if env_name and env_name not in names:
                    names.append(env_name)
        except (json.JSONDecodeError, AttributeError):
            pass
    return names


def quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "").replace("\r", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hermes Companion secrets and .env")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / ".env"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} already exists; use --force to replace it")
    email = (args.email or input("Initial administrator email: ")).strip().lower()
    password = args.password or getpass.getpass("Initial administrator password (16+ recommended): ")
    if "@" not in email:
        raise SystemExit("A valid email is required")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    lines = [
        "APP_ENV=production",
        f"APP_SECRET={secrets.token_urlsafe(48)}",
        "DATABASE_PATH=./services/bridge/data/hermes_companion.db",
        "ACCESS_TOKEN_MINUTES=20",
        "REFRESH_TOKEN_DAYS=30",
        "CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,https://localhost,tauri://localhost,http://tauri.localhost,https://tauri.localhost",
        "WEB_DIST_DIR=./apps/web/dist",
        "TRUST_PROXY_HEADERS=false",
        "MAX_REQUEST_BODY_BYTES=2097152",
        f"INITIAL_ADMIN_EMAIL={quote(email)}",
        "INITIAL_ADMIN_PASSWORD=",
        "HERMES_BASE_URL=http://127.0.0.1:8642",
        "HERMES_PROFILES_FILE=./config/profiles.json",
        "HERMES_REQUEST_TIMEOUT_SECONDS=60",
        "HERMES_CONNECT_TIMEOUT_SECONDS=10",
        "HERMES_SSE_MAX_SECONDS=21600",
        "HERMES_SERVE_URL=",
        "HERMES_SERVE_SESSION_TOKEN=",
        "GATEWAY_TICKET_SECONDS=60",
        "GATEWAY_CONNECT_TIMEOUT_SECONDS=10",
        "GATEWAY_MAX_MESSAGE_BYTES=2097152",
        # GATEWAY_ALLOWED_METHODS is deliberately omitted: an empty value would override the
        # bridge's reviewed default allowlist with an empty one (default-deny everything).
        "UPLOAD_ROOT=./services/bridge/data/uploads",
        "MAX_UPLOAD_BYTES=26214400",
        "UPLOAD_RETENTION_DAYS=30",
        "UPLOAD_SCAN_COMMAND=",
        "UPLOAD_SCAN_TIMEOUT_SECONDS=30",
        "UPLOAD_ALLOWED_EXTENSIONS=.txt,.md,.csv,.tsv,.json,.jsonl,.yaml,.yml,.toml,.py,.js,.mjs,.cjs,.ts,.tsx,.jsx,.html,.css,.sql,.xml,.log,.ini,.cfg,.mq5,.mqh,.set,.pdf,.png,.jpg,.jpeg,.webp,.gif",
        "BACKUP_ROOT=./backups",
        "NOTIFICATION_RETENTION_DAYS=30",
        "ALLOW_WIDE_APPROVALS=false",
        "PUBLIC_APP_URL=",
    ]
    for env_name in profile_env_names(root):
        lines.append(f"{env_name}={secrets.token_urlsafe(36)}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass

    # Create the first user directly. The plaintext password is never written to .env.
    # The database and hashing layer use only the Python standard library.
    sys.path.insert(0, str(root / "services" / "bridge"))
    from app.db import Database
    database_path = root / "services" / "bridge" / "data" / "hermes_companion.db"
    created = Database(database_path).bootstrap_admin(email, password)
    print(target)
    print("Initial administrator created." if created else "Administrator database already contained a user.")
    print("The plaintext password was never written to .env.")


if __name__ == "__main__":
    main()
