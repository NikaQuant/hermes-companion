"""WebAuthn / passkey support for the Companion bridge.

The fido2 library performs every cryptographic ceremony (challenge handling, origin
checking, signature verification, attestation validation); this module only adapts
its wire format (bytes <-> base64url JSON), keeps a single-process challenge store
with expiry, and builds one Fido2Server per settings object.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Mapping
from typing import Any

from fido2.server import Fido2Server
from fido2.utils import websafe_decode, websafe_encode
from fido2.webauthn import AttestedCredentialData, PublicKeyCredentialRpEntity

_CHALLENGE_TTL_SECONDS = 180
_MAX_LIVE_CHALLENGES = 512

_lock = threading.Lock()
_challenges: dict[str, dict[str, Any]] = {}


def server_for(settings: Any) -> Fido2Server:
    return Fido2Server(PublicKeyCredentialRpEntity(id=settings.webauthn_rp_id, name="Hermes Companion"))


def jsonify(value: Any) -> Any:
    """fido2 options -> plain JSON structures (bytes become base64url strings)."""
    if isinstance(value, (bytes, bytearray)):
        return websafe_encode(bytes(value))
    if isinstance(value, Mapping):
        return {str(key): jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonify(item) for item in value]
    return value


def store_challenge(kind: str, state: Any, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        # Sweep expired entries and cap the store against memory abuse.
        for expired in [k for k, v in _challenges.items() if now - v["created"] > _CHALLENGE_TTL_SECONDS]:
            _challenges.pop(expired, None)
        while len(_challenges) >= _MAX_LIVE_CHALLENGES:
            _challenges.pop(next(iter(_challenges)), None)
        _challenges[token] = {"kind": kind, "state": state, "user_id": user_id, "created": now}
    return token


def consume_challenge(token: str, kind: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Atomically remove and return a matching challenge entry (single use)."""
    with _lock:
        entry = _challenges.pop(str(token or ""), None)
    if not entry:
        return None
    if entry["kind"] != kind:
        return None
    if user_id is not None and entry["user_id"] != user_id:
        return None
    if time.monotonic() - entry["created"] > _CHALLENGE_TTL_SECONDS:
        return None
    return entry


def credential_list(rows: list[dict[str, Any]]) -> list[AttestedCredentialData]:
    """Parse stored credentials; a corrupt row is skipped, never a lock-out."""
    result: list[AttestedCredentialData] = []
    for row in rows:
        try:
            result.append(AttestedCredentialData(websafe_decode(row["public_key"])))
        except Exception:  # noqa: BLE001 - one bad row must not break sign-in for the rest
            continue
    return result


def encode(data: bytes) -> str:
    return websafe_encode(data)


def decode(value: str) -> bytes:
    return websafe_decode(value)
