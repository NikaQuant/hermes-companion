from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime


SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_timestamp() -> int:
    return int(utc_now().timestamp())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
        maxmem=128 * 1024 * 1024,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_hash = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        expected = _unb64(raw_hash)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(raw_salt),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
            maxmem=128 * 1024 * 1024,
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


def new_token(bytes_length: int = 32) -> str:
    return secrets.token_urlsafe(bytes_length)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def stable_session_key(app_secret: str, user_id: str, profile: str) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"), f"{user_id}\0{profile}".encode("utf-8"), hashlib.sha256
    ).digest()
    return f"companion-{_b64(digest)[:32]}"
