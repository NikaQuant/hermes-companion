from __future__ import annotations

from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.hermes.client import HermesGateway
from app.main import create_app


def transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def client(settings) -> TestClient:
    app = create_app(settings, hermes_factory=lambda s: HermesGateway(s, transport=httpx.MockTransport(transport)))
    return TestClient(app)


def login(test_client: TestClient, email="nik@example.com", password="test-password-long-enough"):
    response = test_client.post("/api/auth/login", json={
        "email": email, "password": password, "device_id": "", "device_name": "pytest",
    })
    assert response.status_code == 200, response.text
    return response.json()


def auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def configured(settings):
    # The pytest process inherits the real .env at collection time, so force every field.
    return replace(settings, webauthn_rp_id="rp.example.test", vapid_public_key="", vapid_private_key="", vapid_subject="")


def test_webauthn_unconfigured_refuses(test_settings):
    unconfigured = replace(test_settings, webauthn_rp_id="")
    api = client(unconfigured)
    tokens = login(api)
    assert api.post("/api/auth/webauthn/register/options", headers=auth(tokens)).status_code == 503
    assert api.post("/api/auth/webauthn/login/options", json={"email": "nik@example.com"}).status_code == 503


def test_webauthn_register_options_then_bad_attempts(test_settings):
    api = client(configured(test_settings))
    tokens = login(api)
    headers = auth(tokens)

    options = api.post("/api/auth/webauthn/register/options", headers=headers)
    assert options.status_code == 200, options.text
    body = options.json()
    assert body["token"]
    public_key = body["options"]["publicKey"]
    assert public_key["rp"]["id"] == "rp.example.test"
    assert public_key["challenge"]
    assert public_key["user"]["id"]

    # Unknown/absent challenge token must be rejected.
    bad = api.post("/api/auth/webauthn/register", headers=headers, json={
        "token": "does-not-exist", "label": "test", "response": {"id": "x"},
    })
    assert bad.status_code == 401

    # A real token with a garbage client response must fail validation, not crash.
    invalid = api.post("/api/auth/webauthn/register", headers=headers, json={
        "token": body["token"], "label": "test",
        "response": {"id": "abc", "rawId": "abc", "type": "public-key",
                     "response": {"clientDataJSON": "abc", "attestationObject": "abc"}},
    })
    assert invalid.status_code == 422

    # The consumed token must not work a second time (single-use challenges).
    replay = api.post("/api/auth/webauthn/register", headers=headers, json={
        "token": body["token"], "label": "test", "response": {"id": "x"},
    })
    assert replay.status_code == 401

    # GET must not look like success (the PWA used to GET this path and receive HTML 200).
    assert api.get("/api/auth/webauthn/register/options", headers=headers).status_code in {404, 405}


def test_webauthn_login_options_and_failures(test_settings):
    api = client(configured(test_settings))
    tokens = login(api)
    headers = auth(tokens)
    app = api.app.state.companion

    # Unknown email behaves exactly like "no passkey": generic 401.
    assert api.post("/api/auth/webauthn/login/options", json={"email": "ghost@example.com"}).status_code == 401
    # Known email with zero credentials: same generic 401.
    assert api.post("/api/auth/webauthn/login/options", json={"email": "nik@example.com"}).status_code == 401

    # Give the user a structurally valid credential so options are produced.
    from cryptography.hazmat.primitives.asymmetric import ec
    from fido2.cose import ES256
    from fido2.server import Fido2Server
    from fido2.utils import websafe_encode
    from fido2.webauthn import AttestedCredentialData, PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity

    app_state = api.app.state.companion
    user = app_state.db.get_user_by_email("nik@example.com")
    server = Fido2Server(PublicKeyCredentialRpEntity(id="rp.example.test", name="Hermes Companion"))
    options, ceremony_state = server.register_begin(
        PublicKeyCredentialUserEntity(id=user["id"].encode(), name=user["email"], display_name=user["email"])
    )
    credential_blob = websafe_encode(
        bytes(AttestedCredentialData.create(
            bytes(16), b"fake-credential-id",
            ES256.from_cryptography_key(ec.generate_private_key(ec.SECP256R1()).public_key()),
        ))
    )
    app_state.db.add_webauthn_credential(
        user_id=user["id"], credential_id=websafe_encode(b"fake-credential-id"),
        public_key=credential_blob, label="pytest",
    )
    login_options = api.post("/api/auth/webauthn/login/options", json={"email": "nik@example.com"})
    assert login_options.status_code == 200
    assert login_options.json()["options"]["publicKey"]["challenge"]
    assert login_options.json()["options"]["publicKey"]["allowCredentials"]

    # A bogus login response must be rejected without crashing.
    bad = api.post("/api/auth/webauthn/login", json={
        "token": login_options.json()["token"],
        "response": {"id": "abc", "rawId": websafe_encode(b"fake-credential-id"), "type": "public-key",
                     "response": {"clientDataJSON": "abc", "authenticatorData": "abc", "signature": "abc"}},
    })
    assert bad.status_code == 401
    # Consumed token is now gone.
    assert api.post("/api/auth/webauthn/login", json={
        "token": login_options.json()["token"], "response": {"id": "abc"},
    }).status_code == 401


def test_webauthn_list_and_remove(test_settings):
    api = client(configured(test_settings))
    tokens = login(api)
    headers = auth(tokens)
    app = api.app.state.companion
    user = app.db.get_user_by_email("nik@example.com")
    record = app.db.add_webauthn_credential(
        user_id=user["id"], credential_id="cred-list-test", public_key="c2VjcmV0", label="Key A",
    )

    listing = api.get("/api/auth/webauthn", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["available"] is True
    assert body["rp_id"] == "rp.example.test"
    assert [item["label"] for item in body["credentials"]] == ["Key A"]

    assert api.delete(f"/api/auth/webauthn/{record['id']}", headers=headers).status_code == 200
    assert api.get("/api/auth/webauthn", headers=headers).json()["credentials"] == []
    assert api.delete(f"/api/auth/webauthn/{record['id']}", headers=headers).status_code == 404
