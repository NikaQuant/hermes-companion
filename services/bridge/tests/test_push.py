from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app.hermes.client import HermesGateway
from app.main import create_app
from app.push import broadcast, push_enabled


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


def test_push_key_requires_configuration(test_settings):
    # The pytest process inherits the real .env at collection time (app.main import),
    # so "unconfigured" must be forced explicitly rather than assumed.
    unconfigured = replace(test_settings, vapid_public_key="", vapid_private_key="", vapid_subject="")
    api = client(unconfigured)
    tokens = login(api)
    assert api.get("/api/push/key", headers=auth(tokens)).status_code == 503
    configured = replace(
        test_settings, vapid_public_key="a" * 43, vapid_private_key="b" * 43, vapid_subject="mailto:t@example.com",
    )
    assert push_enabled(configured)
    api = client(configured)
    tokens = login(api)
    response = api.get("/api/push/key", headers=auth(tokens))
    assert response.status_code == 200
    assert response.json()["public_key"] == "a" * 43


def test_push_subscribe_list_unsubscribe_by_endpoint(test_settings):
    configured = replace(
        test_settings, vapid_public_key="a" * 43, vapid_private_key="b" * 43, vapid_subject="mailto:t@example.com",
    )
    api = client(configured)
    tokens = login(api)
    headers = auth(tokens)

    rejected = api.post("/api/push/subscribe", json={"endpoint": "http://insecure", "p256dh": "a" * 32, "auth": "b" * 16}, headers=headers)
    assert rejected.status_code == 422

    created = api.post("/api/push/subscribe", json={
        "endpoint": "https://push.example.test/sub/1", "p256dh": "a" * 64, "auth": "b" * 22,
    }, headers=headers)
    assert created.status_code == 200, created.text

    # Re-subscribing the same endpoint must not duplicate rows.
    again = api.post("/api/push/subscribe", json={
        "endpoint": "https://push.example.test/sub/1", "p256dh": "c" * 64, "auth": "d" * 22,
    }, headers=headers)
    assert again.status_code == 200

    listed = api.get("/api/push/subscriptions", headers=headers).json()["subscriptions"]
    assert len(listed) == 1

    removed = api.request("DELETE", "/api/push/subscribe", json={
        "endpoint": "https://push.example.test/sub/1",
    }, headers=headers)
    assert removed.status_code == 200
    assert api.get("/api/push/subscriptions", headers=headers).json()["subscriptions"] == []
    # Idempotent refusal for unknown endpoints.
    assert api.request("DELETE", "/api/push/subscribe", json={
        "endpoint": "https://push.example.test/sub/missing",
    }, headers=headers).status_code == 404


def test_push_broadcast_prunes_gone_subscriptions(test_settings, monkeypatch):
    configured = replace(
        test_settings, vapid_public_key="a" * 43, vapid_private_key="b" * 43, vapid_subject="mailto:t@example.com",
    )
    api = client(configured)
    tokens = login(api)
    user = api.get("/api/auth/me", headers=auth(tokens)).json()
    api.post("/api/push/subscribe", json={
        "endpoint": "https://push.example.test/gone", "p256dh": "a" * 64, "auth": "b" * 22,
    }, headers=auth(tokens))

    class GoneResponse:
        status_code = 410

    def fake_webpush(**kwargs):
        raise WebPushException("subscription gone", response=GoneResponse())

    import app.push as push_module

    monkeypatch.setattr(push_module, "webpush", fake_webpush)
    notification = {
        "id": "n1", "user_id": user["id"], "title": "Run completed", "message": "done",
        "severity": "success", "profile": "default", "kind": "run.completed",
    }
    asyncio.run(broadcast(api.app.state.companion, notification))
    app = api.app.state.companion
    assert app.db.get_push_subscription_by_endpoint("https://push.example.test/gone") is None
