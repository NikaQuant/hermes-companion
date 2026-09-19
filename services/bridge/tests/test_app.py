from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.hermes.client import HermesGateway
from app.main import create_app


def _mock_transport(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("authorization", "").startswith("Bearer ")
    if request.url.path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path.endswith("/api/sessions"):
        return httpx.Response(200, json={"sessions": [{"id": "session-1", "title": "Test"}]})
    if request.url.path.endswith("/v1/runs"):
        assert request.headers.get("idempotency-key")
        return httpx.Response(202, json={"run_id": "run-1", "status": "queued"})
    if request.url.path.endswith("/events"):
        body = b'data: {"event":"assistant.delta","delta":"hello"}\n\n' + b'data: {"event":"run.completed"}\n\n'
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    if request.url.path.endswith(("/approval", "/stop", "/steer")):
        return httpx.Response(200, json={"ok": True})
    return httpx.Response(404, json={"error": "not found"})


def _client(settings):
    transport = httpx.MockTransport(_mock_transport)
    app = create_app(settings, hermes_factory=lambda s: HermesGateway(s, transport=transport))
    return TestClient(app)


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "nik@example.com", "password": "test-password-long-enough"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_login_profiles_and_sessions(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        profiles = client.get("/api/profiles", headers=headers)
        assert profiles.status_code == 200
        assert [p["slug"] for p in profiles.json()["profiles"]] == ["default", "mentos"]
        sessions = client.get("/api/profiles/default/sessions", headers=headers)
        assert sessions.status_code == 200
        assert sessions.json()["sessions"][0]["id"] == "session-1"


def test_run_and_sse_proxy(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/profiles/default/runs",
            headers=headers,
            json={"input": "hello", "session_id": "session-1"},
        )
        assert response.status_code == 200
        assert response.json()["run_id"] == "run-1"
        with client.stream("GET", "/api/profiles/default/runs/run-1/events", headers=headers) as stream:
            text = "".join(stream.iter_text())
        assert "assistant.delta" in text
        assert "run.completed" in text


def test_unconfigured_or_safety_profile_is_not_exposed(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/profiles/live-safe/sessions", headers=headers).status_code == 404



def test_refresh_rotates_token_and_old_refresh_fails(test_settings):
    with _client(test_settings) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "nik@example.com", "password": "test-password-long-enough"},
        ).json()
        old_refresh = login["refresh_token"]
        rotated = client.post(
            "/api/auth/refresh",
            json={"refresh_token": old_refresh, "device_name": "pytest"},
        )
        assert rotated.status_code == 200
        assert rotated.json()["refresh_token"] != old_refresh
        reused = client.post(
            "/api/auth/refresh",
            json={"refresh_token": old_refresh, "device_name": "pytest"},
        )
        assert reused.status_code == 401


def test_logout_revokes_access_token(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        assert client.post("/api/auth/logout", headers=headers, json={}).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_mobile_approval_scope_is_fail_closed(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        blocked = client.post(
            "/api/profiles/default/runs/run-1/approval",
            headers=headers,
            json={"choice": "always", "resolve_all": False},
        )
        assert blocked.status_code == 403
        allowed = client.post(
            "/api/profiles/default/runs/run-1/approval",
            headers=headers,
            json={"choice": "once", "resolve_all": False},
        )
        assert allowed.status_code == 200
        assert allowed.json() == {"ok": True}


def test_handoff_is_profile_checked_and_one_time(test_settings):
    with _client(test_settings) as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        forbidden = client.post(
            "/api/handoff",
            headers=headers,
            json={"profile": "live-safe", "session_id": "session-1"},
        )
        assert forbidden.status_code == 404
        created = client.post(
            "/api/handoff",
            headers=headers,
            json={"profile": "default", "session_id": "session-1"},
        )
        assert created.status_code == 200
        handoff = created.json()["token"]
        first = client.get(f"/api/handoff/{handoff}", headers=headers)
        assert first.status_code == 200
        assert first.json() == {"profile": "default", "session_id": "session-1"}
        assert client.get(f"/api/handoff/{handoff}", headers=headers).status_code == 404


def test_security_headers_health_version_and_request_limit(test_settings):
    with _client(test_settings) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.3.2"
        assert health.headers["x-content-type-options"] == "nosniff"
        assert health.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
        assert health.headers["cache-control"] == "no-store"
        too_large = client.post(
            "/api/auth/login",
            headers={"content-length": str(test_settings.max_request_body_bytes + 1)},
            json={"email": "nik@example.com", "password": "x"},
        )
        assert too_large.status_code == 413
