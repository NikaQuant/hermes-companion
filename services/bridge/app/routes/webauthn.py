"""Passkey (WebAuthn) routes: register, list, remove, and passwordless login.

Password login always remains available as a fallback. A passkey is bound to the
RP ID (the public HTTPS host), so passkey sign-in happens on the tailnet URL;
local-loopback users keep using the password.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import webauthn as wa
from ..dependencies import client_ip, current_user, state
from .auth import _issue_pair

router = APIRouter(prefix="/api/auth/webauthn", tags=["webauthn"])


class WebauthnRegisterRequest(BaseModel):
    token: str
    label: str = ""
    response: dict


class WebauthnLoginOptionsRequest(BaseModel):
    email: str


class WebauthnLoginRequest(BaseModel):
    token: str
    device_name: str = ""
    response: dict


def _require_webauthn(request: Request):
    app = state(request)
    if not app.settings.webauthn_available:
        raise HTTPException(status_code=503, detail="Passkeys are not configured on this bridge")
    return app


@router.post("/register/options")
def register_options(request: Request, user: dict = Depends(current_user)) -> dict:
    app = _require_webauthn(request)
    from fido2.webauthn import PublicKeyCredentialUserEntity

    credentials = wa.credential_list(app.db.list_webauthn_credentials(user["id"]))
    options, ceremony_state = wa.server_for(app.settings).register_begin(
        PublicKeyCredentialUserEntity(
            id=user["id"].encode("utf-8"), name=user["email"], display_name=user["email"]
        ),
        credentials,
        user_verification="preferred",
    )
    token = wa.store_challenge("register", ceremony_state, user["id"])
    return {"options": wa.jsonify(options), "token": token}


@router.post("/register")
def register(request: Request, body: WebauthnRegisterRequest, user: dict = Depends(current_user)) -> dict:
    app = _require_webauthn(request)
    entry = wa.consume_challenge(body.token, "register", user["id"])
    if entry is None:
        raise HTTPException(status_code=401, detail="Registration session expired or invalid")
    try:
        auth_data = wa.server_for(app.settings).register_complete(entry["state"], response=body.response)
    except Exception as exc:  # noqa: BLE001 - fido2 raises many validation types
        raise HTTPException(status_code=422, detail=f"Passkey registration failed: {str(exc)[:200]}") from exc
    credential_data = auth_data.credential_data
    label = (body.label or "").strip() or "Passkey"
    try:
        record = app.db.add_webauthn_credential(
            user_id=user["id"],
            credential_id=wa.encode(credential_data.credential_id),
            public_key=wa.encode(bytes(credential_data)),
            sign_count=getattr(auth_data, "sign_count", 0) or 0,
            label=label,
            transports=",".join(body.response.get("transports") or []) if isinstance(body.response.get("transports"), list) else "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    app.db.audit(
        event="auth.webauthn_registered", user_id=user["id"], ip=client_ip(request),
        metadata={"credential_id": record["id"], "label": label},
    )
    return {"id": record["id"], "label": label}


@router.get("")
def list_credentials(request: Request, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    rows = app.db.list_webauthn_credentials(user["id"])
    return {
        "available": app.settings.webauthn_available,
        "rp_id": app.settings.webauthn_rp_id or None,
        "credentials": [
            {
                "id": row["id"],
                "label": row["label"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
            }
            for row in rows
        ],
    }


@router.delete("/{credential_id}")
def remove_credential(request: Request, credential_id: str, user: dict = Depends(current_user)) -> dict:
    app = state(request)
    if not app.db.delete_webauthn_credential(user["id"], credential_id):
        raise HTTPException(status_code=404, detail="Passkey not found")
    app.db.audit(
        event="auth.webauthn_removed", user_id=user["id"], ip=client_ip(request),
        metadata={"credential_id": credential_id},
    )
    return {"ok": True}


@router.post("/login/options")
def login_options(request: Request, body: WebauthnLoginOptionsRequest) -> dict:
    app = _require_webauthn(request)
    user = app.db.get_user_by_email((body.email or "").strip().lower())
    rows = app.db.list_webauthn_credentials(user["id"]) if user else []
    if not user or not rows:
        raise HTTPException(status_code=401, detail="Invalid email or no passkey registered")
    options, ceremony_state = wa.server_for(app.settings).authenticate_begin(
        wa.credential_list(rows), user_verification="preferred"
    )
    token = wa.store_challenge("login", ceremony_state, user["id"])
    return {"options": wa.jsonify(options), "token": token}


@router.post("/login")
def login(request: Request, body: WebauthnLoginRequest) -> dict:
    app = _require_webauthn(request)
    entry = wa.consume_challenge(body.token, "login")
    if entry is None:
        raise HTTPException(status_code=401, detail="Sign-in session expired or invalid")
    user = app.db.get_user(entry["user_id"])
    if not user or not user.get("active"):
        raise HTTPException(status_code=401, detail="Invalid email or no passkey registered")
    rows = app.db.list_webauthn_credentials(user["id"])
    try:
        auth_data = wa.server_for(app.settings).authenticate_complete(
            entry["state"], wa.credential_list(rows), response=body.response
        )
    except Exception as exc:  # noqa: BLE001 - fido2 raises many validation types
        app.db.audit(
            event="auth.webauthn_failed", user_id=user["id"], ip=client_ip(request),
            metadata={"error": type(exc).__name__},
        )
        raise HTTPException(status_code=401, detail="Passkey verification failed") from exc

    raw_id = str(body.response.get("rawId") or body.response.get("id") or "")
    record = app.db.get_webauthn_credential_by_credential_id(raw_id)
    if not record or record["user_id"] != user["id"]:
        raise HTTPException(status_code=401, detail="Passkey verification failed")
    app.db.mark_webauthn_used(record["id"], getattr(auth_data, "sign_count", record["sign_count"]) or 0)
    app.db.audit(
        event="auth.webauthn_login", user_id=user["id"], ip=client_ip(request),
        metadata={"credential_id": record["id"]},
    )
    return _issue_pair(request, user, (body.device_name or "").strip()[:120] or "Passkey sign-in")
