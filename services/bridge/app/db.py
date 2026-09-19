from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

from .security import hash_password, token_hash, utc_now, utc_timestamp


_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL DEFAULT 0,
    last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('access', 'refresh')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    created_at INTEGER NOT NULL,
    device_id TEXT NOT NULL DEFAULT '',
    device_name TEXT NOT NULL DEFAULT '',
    last_used_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_lookup ON auth_tokens(token_hash, kind, expires_at);

CREATE TABLE IF NOT EXISTS user_profile_access (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, profile)
);

CREATE TABLE IF NOT EXISTS handoffs (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    session_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gateway_tickets (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT,
    read_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe
    ON notifications(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL UNIQUE,
    endpoint_hash TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS webauthn_credentials (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT '',
    transports TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_webauthn_credentials_user ON webauthn_credentials(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS saved_prompts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    profile TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_prompts_user ON saved_prompts(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS session_metadata (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    session_id TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, profile, session_id)
);
CREATE INDEX IF NOT EXISTS idx_session_metadata_user ON session_metadata(user_id, profile, pinned DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    scan_status TEXT NOT NULL DEFAULT 'not_configured',
    scan_detail TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id, profile, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    event TEXT NOT NULL,
    profile TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    ip TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event, created_at DESC);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}

    @classmethod
    def _ensure_column(cls, connection: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
        if name not in cls._columns(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def initialize(self) -> None:
        with self._lock, self.connect() as connection:
            connection.executescript(_SCHEMA)
            # In-place upgrades from v0.1/v0.2 databases.
            self._ensure_column(connection, "users", "updated_at", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "users", "last_login_at", "INTEGER")
            self._ensure_column(connection, "auth_tokens", "device_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "auth_tokens", "last_used_at", "INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_tokens_device "
                "ON auth_tokens(user_id, device_id, kind, expires_at)"
            )
            connection.execute("UPDATE users SET updated_at=created_at WHERE updated_at=0")
            connection.execute("UPDATE auth_tokens SET last_used_at=created_at WHERE last_used_at=0")
            connection.execute(
                "UPDATE auth_tokens SET device_id=id WHERE device_id='' OR device_id IS NULL"
            )

    # ── users / access ──────────────────────────────────────────────────────────

    def bootstrap_admin(self, email: str, password: str) -> bool:
        if not email or not password:
            return False
        now = utc_timestamp()
        with self._lock, self.connect() as connection:
            existing = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            if existing:
                return False
            connection.execute(
                "INSERT INTO users(id,email,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,?,1,?,?)",
                (str(uuid.uuid4()), email.lower(), hash_password(password), "admin", now, now),
            )
            return True

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id,email,password_hash,role,active,created_at,updated_at,last_login_at "
                "FROM users WHERE email=?",
                (email.lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id: str, *, include_hash: bool = False) -> dict[str, Any] | None:
        fields = "id,email,role,active,created_at,updated_at,last_login_at"
        if include_hash:
            fields += ",password_hash"
        with self.connect() as connection:
            row = connection.execute(f"SELECT {fields} FROM users WHERE id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id,email,role,active,created_at,updated_at,last_login_at FROM users "
                "ORDER BY created_at ASC"
            ).fetchall()
        users = [dict(row) for row in rows]
        for user in users:
            user["profiles"] = self.list_user_profiles(user["id"])
        return users

    def create_user(
        self, *, email: str, password: str, role: str = "user", active: bool = True,
        profiles: list[str] | None = None,
    ) -> dict[str, Any]:
        if role not in {"admin", "user"}:
            raise ValueError("Role must be admin or user")
        now = utc_timestamp()
        user_id = str(uuid.uuid4())
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO users(id,email,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (user_id, email.lower(), hash_password(password), role, int(active), now, now),
            )
            for profile in sorted(set(profiles or [])):
                connection.execute(
                    "INSERT INTO user_profile_access(user_id,profile,created_at) VALUES(?,?,?)",
                    (user_id, profile, now),
                )
        return self.get_user(user_id) or {}

    def update_user(
        self, user_id: str, *, role: str | None = None, active: bool | None = None,
        profiles: list[str] | None = None,
    ) -> dict[str, Any] | None:
        if role is not None and role not in {"admin", "user"}:
            raise ValueError("Role must be admin or user")
        now = utc_timestamp()
        with self._lock, self.connect() as connection:
            if not connection.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                return None
            if role is not None:
                connection.execute("UPDATE users SET role=?,updated_at=? WHERE id=?", (role, now, user_id))
            if active is not None:
                connection.execute(
                    "UPDATE users SET active=?,updated_at=? WHERE id=?", (int(active), now, user_id)
                )
                if not active:
                    connection.execute(
                        "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                        (now, user_id),
                    )
            if profiles is not None:
                connection.execute("DELETE FROM user_profile_access WHERE user_id=?", (user_id,))
                for profile in sorted(set(profiles)):
                    connection.execute(
                        "INSERT INTO user_profile_access(user_id,profile,created_at) VALUES(?,?,?)",
                        (user_id, profile, now),
                    )
        user = self.get_user(user_id)
        if user:
            user["profiles"] = self.list_user_profiles(user_id)
        return user

    def set_password(self, user_id: str, password: str, *, revoke_tokens: bool = True) -> bool:
        now = utc_timestamp()
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
                (hash_password(password), now, user_id),
            )
            if cursor.rowcount and revoke_tokens:
                connection.execute(
                    "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                    (now, user_id),
                )
            return bool(cursor.rowcount)

    def delete_user(self, user_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute("DELETE FROM users WHERE id=?", (user_id,))
            return bool(cursor.rowcount)

    def mark_login(self, user_id: str) -> None:
        now = utc_timestamp()
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE users SET last_login_at=?,updated_at=? WHERE id=?", (now, now, user_id)
            )

    def list_user_profiles(self, user_id: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT profile FROM user_profile_access WHERE user_id=? ORDER BY profile", (user_id,)
            ).fetchall()
        return [str(row["profile"]) for row in rows]

    def user_profile_allowed(self, user: dict[str, Any], profile: str) -> bool:
        if user.get("role") == "admin":
            return True
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM user_profile_access WHERE user_id=? AND profile=?",
                (user["id"], profile),
            ).fetchone() is not None

    # ── auth tokens / devices ───────────────────────────────────────────────────

    def create_token(
        self, *, user_id: str, kind: str, token: str, ttl: timedelta,
        device_id: str = "", device_name: str = "",
    ) -> int:
        now = utc_timestamp()
        expires = int((utc_now() + ttl).timestamp())
        device_id = (device_id or str(uuid.uuid4()))[:120]
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO auth_tokens(id,user_id,kind,token_hash,expires_at,created_at,device_id,device_name,last_used_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), user_id, kind, token_hash(token), expires, now,
                    device_id, device_name[:120], now,
                ),
            )
        return expires

    def resolve_token(self, token: str, kind: str = "access") -> dict[str, Any] | None:
        now = utc_timestamp()
        hashed = token_hash(token)
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT u.id,u.email,u.role,u.active,t.id AS token_id,t.expires_at,t.device_id,t.device_name "
                "FROM auth_tokens t JOIN users u ON u.id=t.user_id "
                "WHERE t.token_hash=? AND t.kind=? AND t.revoked_at IS NULL AND t.expires_at>?",
                (hashed, kind, now),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE auth_tokens SET last_used_at=? WHERE token_hash=?", (now, hashed)
                )
            return dict(row) if row else None

    def rotate_refresh_token(
        self, *, old_token: str, new_access: str, new_refresh: str, access_ttl: timedelta,
        refresh_ttl: timedelta, device_id: str = "", device_name: str = "",
    ) -> tuple[dict[str, Any], int, int, str] | None:
        now = utc_timestamp()
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT t.id,t.user_id,t.device_id,t.device_name,u.email,u.role,u.active FROM auth_tokens t "
                "JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.kind='refresh' "
                "AND t.revoked_at IS NULL AND t.expires_at>?",
                (token_hash(old_token), now),
            ).fetchone()
            if not row or not row["active"]:
                return None
            connection.execute("UPDATE auth_tokens SET revoked_at=? WHERE id=?", (now, row["id"]))
            user_id = row["user_id"]
            # Refresh rotation stays bound to the original device. A stolen refresh token
            # must not escape later device revocation by choosing a new device identifier.
            resolved_device_id = (row["device_id"] or device_id or str(uuid.uuid4()))[:120]
            resolved_device_name = (device_name or row["device_name"] or "")[:120]
            access_expires = int((utc_now() + access_ttl).timestamp())
            refresh_expires = int((utc_now() + refresh_ttl).timestamp())
            for kind, token, expires in (
                ("access", new_access, access_expires),
                ("refresh", new_refresh, refresh_expires),
            ):
                connection.execute(
                    "INSERT INTO auth_tokens(id,user_id,kind,token_hash,expires_at,created_at,device_id,device_name,last_used_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), user_id, kind, token_hash(token), expires, now,
                        resolved_device_id, resolved_device_name, now,
                    ),
                )
            user = {k: row[k] for k in ("user_id", "email", "role", "active")}
            user["id"] = user.pop("user_id")
            return user, access_expires, refresh_expires, resolved_device_id

    def revoke_token(self, token: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE auth_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (utc_timestamp(), token_hash(token)),
            )

    def revoke_all_user_tokens(self, user_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (utc_timestamp(), user_id),
            )

    def list_devices(self, user_id: str) -> list[dict[str, Any]]:
        now = utc_timestamp()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT device_id,MAX(device_name) AS device_name,MIN(created_at) AS first_seen_at,"
                "MAX(last_used_at) AS last_used_at,MAX(expires_at) AS refresh_expires_at,"
                "SUM(CASE WHEN revoked_at IS NULL AND expires_at>? THEN 1 ELSE 0 END) AS active_tokens "
                "FROM auth_tokens WHERE user_id=? GROUP BY device_id ORDER BY last_used_at DESC",
                (now, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_device(self, user_id: str, device_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND device_id=? AND revoked_at IS NULL",
                (utc_timestamp(), user_id, device_id),
            )
            return bool(cursor.rowcount)

    # ── handoff / gateway tickets ───────────────────────────────────────────────

    def create_handoff(
        self, *, token: str, user_id: str, profile: str, session_id: str, ttl_seconds: int = 300
    ) -> int:
        return self._create_one_time_token(
            table="handoffs", token=token, user_id=user_id, profile=profile,
            ttl_seconds=ttl_seconds, extra=("session_id", session_id),
        )

    def consume_handoff(self, *, token: str, user_id: str) -> dict[str, Any] | None:
        return self._consume_one_time_token("handoffs", token=token, user_id=user_id, fields="session_id")

    def create_gateway_ticket(
        self, *, token: str, user_id: str, profile: str, ttl_seconds: int
    ) -> int:
        return self._create_one_time_token(
            table="gateway_tickets", token=token, user_id=user_id, profile=profile,
            ttl_seconds=ttl_seconds,
        )

    def consume_gateway_ticket(self, token: str) -> dict[str, Any] | None:
        return self._consume_one_time_token("gateway_tickets", token=token, user_id=None)

    def _create_one_time_token(
        self, *, table: str, token: str, user_id: str, profile: str, ttl_seconds: int,
        extra: tuple[str, str] | None = None,
    ) -> int:
        if table not in {"handoffs", "gateway_tickets"}:
            raise ValueError("Unsupported token table")
        now = utc_timestamp()
        expires = now + ttl_seconds
        columns = "id,token_hash,user_id,profile,expires_at,created_at"
        placeholders = "?,?,?,?,?,?"
        values: list[Any] = [str(uuid.uuid4()), token_hash(token), user_id, profile, expires, now]
        if extra:
            columns += f",{extra[0]}"
            placeholders += ",?"
            values.append(extra[1])
        with self._lock, self.connect() as connection:
            connection.execute(f"INSERT INTO {table}({columns}) VALUES({placeholders})", values)
        return expires

    def _consume_one_time_token(
        self, table: str, *, token: str, user_id: str | None, fields: str = ""
    ) -> dict[str, Any] | None:
        if table not in {"handoffs", "gateway_tickets"}:
            raise ValueError("Unsupported token table")
        now = utc_timestamp()
        field_sql = f",{fields}" if fields else ""
        where_user = " AND user_id=?" if user_id is not None else ""
        params: list[Any] = [token_hash(token)]
        if user_id is not None:
            params.append(user_id)
        params.append(now)
        with self._lock, self.connect() as connection:
            row = connection.execute(
                f"SELECT id,user_id,profile,expires_at{field_sql} FROM {table} WHERE token_hash=?"
                f"{where_user} AND consumed_at IS NULL AND expires_at>?",
                params,
            ).fetchone()
            if not row:
                return None
            consumed = connection.execute(
                f"UPDATE {table} SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                (now, row["id"]),
            )
            if consumed.rowcount != 1:
                return None
            return dict(row)

    # ── push subscriptions ──────────────────────────────────────────────────────

    def add_push_subscription(
        self, *, user_id: str, endpoint: str, p256dh: str, auth: str, user_agent: str = "",
    ) -> dict[str, Any]:
        now = utc_timestamp()
        subscription_id = str(uuid.uuid4())
        endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO push_subscriptions(id,user_id,endpoint,endpoint_hash,p256dh,auth,user_agent,created_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET "
                "user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth, "
                "user_agent=excluded.user_agent",
                (
                    subscription_id, user_id, endpoint[:2000], endpoint_hash,
                    p256dh[:512], auth[:512], user_agent[:240], now,
                ),
            )
        return self.get_push_subscription_by_endpoint(endpoint) or {}

    def get_push_subscription_by_endpoint(self, endpoint: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM push_subscriptions WHERE endpoint=?", (endpoint[:2000],)
            ).fetchone()
            return dict(row) if row else None

    def list_push_subscriptions(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM push_subscriptions WHERE user_id=? ORDER BY created_at ASC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_push_subscription(self, user_id: str, subscription_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM push_subscriptions WHERE id=? AND user_id=?", (subscription_id, user_id)
            )
            return bool(cursor.rowcount)

    def drop_push_endpoint(self, endpoint: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint[:2000],))

    def touch_push_endpoint(self, endpoint: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE push_subscriptions SET last_used_at=? WHERE endpoint=?",
                (utc_timestamp(), endpoint[:2000]),
            )

    # ── webauthn credentials ────────────────────────────────────────────────────

    def add_webauthn_credential(
        self, *, user_id: str, credential_id: str, public_key: str,
        sign_count: int = 0, label: str = "", transports: str = "",
    ) -> dict[str, Any]:
        now = utc_timestamp()
        credential_row_id = str(uuid.uuid4())
        with self._lock, self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM webauthn_credentials WHERE credential_id=?", (credential_id[:1024],)
            ).fetchone()
            if existing:
                raise ValueError("This passkey is already registered")
            connection.execute(
                "INSERT INTO webauthn_credentials(id,user_id,credential_id,public_key,sign_count,label,transports,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    credential_row_id, user_id, credential_id[:1024], public_key[:4096],
                    max(0, int(sign_count)), label[:120], transports[:240], now,
                ),
            )
        return {"id": credential_row_id}

    def list_webauthn_credentials(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM webauthn_credentials WHERE user_id=? ORDER BY created_at ASC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_webauthn_credential_by_credential_id(self, credential_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM webauthn_credentials WHERE credential_id=?", (credential_id[:1024],)
            ).fetchone()
            return dict(row) if row else None

    def delete_webauthn_credential(self, user_id: str, credential_row_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM webauthn_credentials WHERE id=? AND user_id=?", (credential_row_id, user_id)
            )
            return bool(cursor.rowcount)

    def mark_webauthn_used(self, credential_row_id: str, sign_count: int) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE webauthn_credentials SET last_used_at=?, sign_count=? WHERE id=?",
                (utc_timestamp(), max(0, int(sign_count)), credential_row_id),
            )

    # ── notifications ───────────────────────────────────────────────────────────

    def create_notification(
        self, *, user_id: str, kind: str, title: str, message: str = "",
        profile: str | None = None, severity: str = "info",
        metadata: dict[str, Any] | None = None, dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        now = utc_timestamp()
        notification_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)[:16000]
        with self._lock, self.connect() as connection:
            if dedupe_key:
                existing = connection.execute(
                    "SELECT id FROM notifications WHERE user_id=? AND dedupe_key=?",
                    (user_id, dedupe_key),
                ).fetchone()
                if existing:
                    connection.execute(
                        "UPDATE notifications SET profile=?,kind=?,title=?,message=?,severity=?,metadata_json=?,"
                        "read_at=NULL,created_at=? WHERE id=?",
                        (
                            profile, kind[:80], title[:240], message[:2000], severity[:20],
                            metadata_json, now, existing["id"],
                        ),
                    )
                    notification_id = existing["id"]
                else:
                    connection.execute(
                        "INSERT INTO notifications(id,user_id,profile,kind,title,message,severity,metadata_json,"
                        "dedupe_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            notification_id, user_id, profile, kind[:80], title[:240], message[:2000],
                            severity[:20], metadata_json, dedupe_key[:240], now,
                        ),
                    )
            else:
                connection.execute(
                    "INSERT INTO notifications(id,user_id,profile,kind,title,message,severity,metadata_json,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        notification_id, user_id, profile, kind[:80], title[:240], message[:2000],
                        severity[:20], metadata_json, now,
                    ),
                )
        return self.get_notification(user_id, notification_id) or {}

    def get_notification(self, user_id: str, notification_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, user_id)
            ).fetchone()
        return self._notification_dict(row) if row else None

    @staticmethod
    def _notification_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json"))
        except json.JSONDecodeError:
            item["metadata"] = {}
        return item

    def list_notifications(
        self, user_id: str, *, limit: int = 100, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        where = "user_id=?" + (" AND read_at IS NULL" if unread_only else "")
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (user_id, max(1, min(limit, 500))),
            ).fetchall()
        return [self._notification_dict(row) for row in rows]

    def unread_notification_count(self, user_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND read_at IS NULL",
                (user_id,),
            ).fetchone()
        return int(row["n"])

    def count_unread_notifications_of_kind(self, user_id: str, kind: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND kind=? AND read_at IS NULL",
                (user_id, kind[:80]),
            ).fetchone()
            return int(row["n"] if row else 0)

    def mark_notification_read(self, user_id: str, notification_id: str, read: bool = True) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET read_at=? WHERE id=? AND user_id=?",
                (utc_timestamp() if read else None, notification_id, user_id),
            )
            return bool(cursor.rowcount)

    def mark_all_notifications_read(self, user_id: str) -> int:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                (utc_timestamp(), user_id),
            )
            return int(cursor.rowcount)

    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM notifications WHERE id=? AND user_id=?", (notification_id, user_id)
            )
            return bool(cursor.rowcount)

    # ── saved prompts / session metadata ────────────────────────────────────────

    def list_prompts(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM saved_prompts WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def create_prompt(self, *, user_id: str, title: str, prompt: str, profile: str | None) -> dict[str, Any]:
        now = utc_timestamp()
        prompt_id = str(uuid.uuid4())
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO saved_prompts(id,user_id,title,prompt,profile,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (prompt_id, user_id, title[:160], prompt, profile, now, now),
            )
        return self.get_prompt(user_id, prompt_id) or {}

    def get_prompt(self, user_id: str, prompt_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM saved_prompts WHERE id=? AND user_id=?", (prompt_id, user_id)
            ).fetchone()
        return dict(row) if row else None

    def update_prompt(
        self, user_id: str, prompt_id: str, *, title: str, prompt: str, profile: str | None
    ) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE saved_prompts SET title=?,prompt=?,profile=?,updated_at=? WHERE id=? AND user_id=?",
                (title[:160], prompt, profile, utc_timestamp(), prompt_id, user_id),
            )
            if not cursor.rowcount:
                return None
        return self.get_prompt(user_id, prompt_id)

    def delete_prompt(self, user_id: str, prompt_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM saved_prompts WHERE id=? AND user_id=?", (prompt_id, user_id)
            )
            return bool(cursor.rowcount)

    def get_session_metadata(self, user_id: str, profile: str, session_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_metadata WHERE user_id=? AND profile=? AND session_id=?",
                (user_id, profile, session_id),
            ).fetchone()
        if not row:
            return {"profile": profile, "session_id": session_id, "pinned": False, "tags": [], "note": ""}
        item = dict(row)
        try:
            item["tags"] = json.loads(item.pop("tags_json"))
        except json.JSONDecodeError:
            item["tags"] = []
        item["pinned"] = bool(item["pinned"])
        return item

    def list_session_metadata(self, user_id: str, profile: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM session_metadata WHERE user_id=? AND profile=? "
                "ORDER BY pinned DESC,updated_at DESC",
                (user_id, profile),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["tags"] = json.loads(item.pop("tags_json"))
            except json.JSONDecodeError:
                item["tags"] = []
            item["pinned"] = bool(item["pinned"])
            result.append(item)
        return result

    def upsert_session_metadata(
        self, *, user_id: str, profile: str, session_id: str, pinned: bool,
        tags: list[str], note: str,
    ) -> dict[str, Any]:
        now = utc_timestamp()
        cleaned_tags = sorted({str(tag).strip()[:40] for tag in tags if str(tag).strip()})[:20]
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO session_metadata(user_id,profile,session_id,pinned,tags_json,note,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,profile,session_id) DO UPDATE SET "
                "pinned=excluded.pinned,tags_json=excluded.tags_json,note=excluded.note,updated_at=excluded.updated_at",
                (
                    user_id, profile, session_id, int(pinned), json.dumps(cleaned_tags), note[:4000], now, now,
                ),
            )
        return self.get_session_metadata(user_id, profile, session_id)

    # ── uploads ─────────────────────────────────────────────────────────────────

    def create_upload(
        self, *, upload_id: str, user_id: str, profile: str, original_name: str,
        stored_name: str, path: str, mime_type: str, size_bytes: int, sha256: str,
        scan_status: str, scan_detail: str,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO uploads(id,user_id,profile,original_name,stored_name,path,mime_type,size_bytes,"
                "sha256,scan_status,scan_detail,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    upload_id, user_id, profile, original_name[:255], stored_name[:255], path,
                    mime_type[:160], size_bytes, sha256, scan_status[:40], scan_detail[:1000], utc_timestamp(),
                ),
            )
        return self.get_upload(user_id, upload_id) or {}

    def get_upload(self, user_id: str, upload_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE id=? AND user_id=?", (upload_id, user_id)
            ).fetchone()
        return dict(row) if row else None

    def find_upload_by_path(self, user_id: str, profile: str, path: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE user_id=? AND profile=? AND path=?",
                (user_id, profile, path),
            ).fetchone()
        return dict(row) if row else None

    def list_uploads(self, user_id: str, *, profile: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where = "user_id=?"
        params: list[Any] = [user_id]
        if profile:
            where += " AND profile=?"
            params.append(profile)
        params.append(max(1, min(limit, 500)))
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM uploads WHERE {where} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_upload(self, user_id: str, upload_id: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE id=? AND user_id=?", (upload_id, user_id)
            ).fetchone()
            if not row:
                return None
            connection.execute("DELETE FROM uploads WHERE id=?", (upload_id,))
            return dict(row)

    def expired_uploads(self, cutoff: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM uploads WHERE created_at<? ORDER BY created_at", (cutoff,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ── audit / maintenance ─────────────────────────────────────────────────────

    def audit(
        self, *, event: str, user_id: str | None = None, profile: str | None = None,
        metadata: dict[str, Any] | None = None, ip: str = "",
    ) -> None:
        safe_metadata = json.dumps(metadata or {}, ensure_ascii=False, default=str)[:16000]
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(user_id,event,profile,metadata_json,ip,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, event[:160], profile, safe_metadata, ip[:100], utc_timestamp()),
            )

    def list_audit(
        self, limit: int = 100, *, event: str | None = None, profile: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event:
            clauses.append("a.event LIKE ?")
            params.append(f"%{event}%")
        if profile:
            clauses.append("a.profile=?")
            params.append(profile)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 2000)))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT a.id,a.event,a.profile,a.metadata_json,a.ip,a.created_at,u.email "
                f"FROM audit_log a LEFT JOIN users u ON u.id=a.user_id {where} "
                "ORDER BY a.id DESC LIMIT ?",
                params,
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except json.JSONDecodeError:
                item["metadata"] = {}
            result.append(item)
        return result

    def stats(self) -> dict[str, Any]:
        tables = (
            "users", "auth_tokens", "notifications", "saved_prompts", "session_metadata",
            "uploads", "handoffs", "gateway_tickets", "audit_log",
        )
        result: dict[str, Any] = {"path": str(self.path), "bytes": self.path.stat().st_size if self.path.exists() else 0}
        with self.connect() as connection:
            result["wal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
            result["counts"] = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
        return result

    def backup_to(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            source = sqlite3.connect(self.path, timeout=30)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        return destination

    def cleanup(self, *, notification_retention_days: int = 30) -> None:
        now = utc_timestamp()
        notification_cutoff = now - max(1, notification_retention_days) * 86400
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM auth_tokens WHERE expires_at<?", (now - 86400,))
            connection.execute("DELETE FROM handoffs WHERE expires_at<?", (now - 86400,))
            connection.execute("DELETE FROM gateway_tickets WHERE expires_at<?", (now - 86400,))
            connection.execute("DELETE FROM notifications WHERE created_at<?", (notification_cutoff,))
