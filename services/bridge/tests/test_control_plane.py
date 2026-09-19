from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.hermes.client import HermesGateway
from app.main import create_app
from app.routes.gateway import _validate_client_frame


def transport(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith('/health') or path.endswith('/health/detailed'):
        return httpx.Response(200, json={'status': 'ok', 'profile': path.split('/')[2] if path.startswith('/p/') else 'default'})
    if path.endswith('/v1/capabilities'):
        return httpx.Response(200, json={'runs': True, 'run_approval': True})
    if path.endswith('/api/model/options'):
        return httpx.Response(200, json={'providers': [{'provider': 'test', 'models': [{'id': 'model-a', 'name': 'Model A'}]}]})
    if path.endswith('/api/jobs'):
        return httpx.Response(200, json={'jobs': [{'id': 'job-1', 'name': 'Daily', 'enabled': True}]})
    if path.endswith('/api/sessions'):
        return httpx.Response(200, json={'sessions': [{'id': 'session-1', 'title': 'Test', 'preview': 'hello'}]})
    if path.endswith('/events'):
        return httpx.Response(200, content=(
            b'data: {"event":"approval.request","description":"Review command"}\n\n'
            b'data: {"event":"run.completed","session_id":"session-1"}\n\n'
        ), headers={'content-type': 'text/event-stream'})
    return httpx.Response(200, json={'ok': True})


def client(settings) -> TestClient:
    app = create_app(settings, hermes_factory=lambda s: HermesGateway(s, transport=httpx.MockTransport(transport)))
    return TestClient(app)


def login(client: TestClient, email='nik@example.com', password='test-password-long-enough', **extra):
    response = client.post('/api/auth/login', json={
        'email': email, 'password': password, 'device_id': extra.get('device_id', ''),
        'device_name': extra.get('device_name', 'pytest'),
    })
    assert response.status_code == 200, response.text
    return response.json()


def auth(tokens):
    return {'Authorization': f"Bearer {tokens['access_token']}"}


def test_admin_users_and_profile_access_are_enforced(test_settings):
    with client(test_settings) as api:
        admin = login(api)
        created = api.post('/api/admin/users', headers=auth(admin), json={
            'email': 'operator@example.com', 'password': 'operator-password-1234',
            'role': 'user', 'profiles': ['mentos'],
        })
        assert created.status_code == 200, created.text
        operator = login(api, 'operator@example.com', 'operator-password-1234')
        profiles = api.get('/api/profiles', headers=auth(operator)).json()['profiles']
        assert [item['slug'] for item in profiles] == ['mentos']
        assert api.get('/api/profiles/default/sessions', headers=auth(operator)).status_code == 404
        assert api.get('/api/profiles/mentos/sessions', headers=auth(operator)).status_code == 200
        assert api.get('/api/admin/users', headers=auth(operator)).status_code == 403


def test_admin_refuses_safety_world_and_self_demotion(test_settings):
    with client(test_settings) as api:
        admin = login(api)
        blocked = api.post('/api/admin/users', headers=auth(admin), json={
            'email': 'blocked@example.com', 'password': 'blocked-password-1234',
            'profiles': ['live-safe'],
        })
        assert blocked.status_code == 400
        me = api.get('/api/auth/me', headers=auth(admin)).json()
        demote = api.patch(f"/api/admin/users/{me['id']}", headers=auth(admin), json={'role': 'user'})
        assert demote.status_code == 400


def test_devices_refresh_and_revoke(test_settings):
    with client(test_settings) as api:
        tokens = login(api, device_id='phone-1', device_name='Pixel test')
        devices = api.get('/api/auth/devices', headers=auth(tokens)).json()['devices']
        assert devices[0]['device_id'] == 'phone-1'
        assert devices[0]['current'] is True
        revoked = api.delete('/api/auth/devices/phone-1', headers=auth(tokens))
        assert revoked.status_code == 200
        assert api.get('/api/auth/me', headers=auth(tokens)).status_code == 401


def test_password_change_revokes_sessions(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        response = api.post('/api/auth/password', headers=auth(tokens), json={
            'current_password': 'test-password-long-enough',
            'new_password': 'a-new-password-long-enough',
        })
        assert response.status_code == 200
        assert api.get('/api/auth/me', headers=auth(tokens)).status_code == 401
        login(api, password='a-new-password-long-enough')


def test_notifications_are_created_from_run_stream(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        with api.stream('GET', '/api/profiles/default/runs/run-1/events', headers=headers) as response:
            assert response.status_code == 200
            assert 'run.completed' in ''.join(response.iter_text())
        data = api.get('/api/notifications', headers=headers).json()
        kinds = {item['kind'] for item in data['notifications']}
        assert {'approval', 'run.completed'} <= kinds
        assert data['unread'] == 2
        assert api.post('/api/notifications/read-all', headers=headers).json()['updated'] == 2
        assert api.get('/api/notifications', headers=headers).json()['unread'] == 0


def test_saved_prompts_and_session_metadata(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        prompt = api.post('/api/prompts', headers=headers, json={
            'title': 'Review', 'prompt': 'Review this code', 'profile': 'default',
        })
        assert prompt.status_code == 200
        prompt_id = prompt.json()['id']
        assert api.put(f'/api/prompts/{prompt_id}', headers=headers, json={
            'title': 'Deep review', 'prompt': 'Review deeply', 'profile': None,
        }).status_code == 200
        assert len(api.get('/api/prompts', headers=headers).json()['prompts']) == 1
        metadata = api.put('/api/profiles/default/session-metadata/session-1', headers=headers, json={
            'pinned': True, 'tags': ['mentos', 'important', 'mentos'], 'note': 'Keep this',
        })
        assert metadata.status_code == 200
        assert metadata.json()['pinned'] is True
        assert metadata.json()['tags'] == ['important', 'mentos']
        assert api.delete(f'/api/prompts/{prompt_id}', headers=headers).status_code == 200


def test_secure_file_inbox(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        uploaded = api.post('/api/files', headers=headers, data={'profile': 'default'}, files={
            'file': ('notes.txt', b'hello hermes', 'text/plain'),
        })
        assert uploaded.status_code == 200, uploaded.text
        item = uploaded.json()
        assert item['sha256']
        assert Path(item['hermes_path']).is_file()
        assert api.get(f"/api/files/{item['id']}/download", headers=headers).content == b'hello hermes'
        blocked = api.post('/api/files', headers=headers, data={'profile': 'default'}, files={
            'file': ('payload.exe', b'MZ', 'application/octet-stream'),
        })
        assert blocked.status_code == 415
        assert api.delete(f"/api/files/{item['id']}", headers=headers).status_code == 200
        assert not Path(item['hermes_path']).exists()


def test_projects_diagnostics_backups_and_audit_filters(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        projects = api.get('/api/projects', headers=headers)
        assert projects.status_code == 200
        assert len(projects.json()['projects']) == 2
        diagnostics = api.get('/api/diagnostics', headers=headers)
        assert diagnostics.status_code == 200
        assert diagnostics.json()['version'] == '0.3.2'
        backup = api.post('/api/backups', headers=headers, json={'label': 'test backup'})
        assert backup.status_code == 200, backup.text
        name = backup.json()['name']
        archive = api.get(f'/api/backups/{name}', headers=headers)
        assert archive.status_code == 200
        assert archive.content.startswith(b'PK')
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
            assert manifest['format'] == 2
            assert manifest['contains_hermes_api_keys'] is False
            restored = test_settings.backup_root / 'inspect-backup.sqlite'
            restored.write_bytes(bundle.read('hermes_companion.sqlite'))
        with sqlite3.connect(restored) as connection:
            assert connection.execute('SELECT COUNT(*) FROM auth_tokens').fetchone()[0] == 0
            assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        audit = api.get('/api/audit?event=backup&limit=50', headers=headers).json()['events']
        assert any(row['event'] == 'backup.created' for row in audit)
        assert api.delete(f'/api/backups/{name}', headers=headers).status_code == 200


def test_gateway_ticket_is_one_time_and_policy_guarded(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        ticket = api.post('/api/gateway/default/ticket', headers=headers)
        assert ticket.status_code == 200
        assert 'session.create' in ticket.json()['allowed_methods']

        app = api.app.state.companion
        user = app.db.resolve_token(tokens['access_token'])
        open_requests: set[str] = set()
        allowed = _validate_client_frame(app, user, 'default', json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'session.list', 'params': {},
        }), open_requests)
        assert json.loads(allowed)['params']['profile'] == 'default'
        denied = _validate_client_frame(app, user, 'default', json.dumps({
            'jsonrpc': '2.0', 'id': 2, 'method': 'config.set', 'params': {},
        }), open_requests)
        assert json.loads(denied)['error']['code'] == -32601
        cross = _validate_client_frame(app, user, 'default', json.dumps({
            'jsonrpc': '2.0', 'id': 3, 'method': 'session.list', 'params': {'profile': 'mentos'},
        }), open_requests)
        assert json.loads(cross)['error']['code'] == 4031

        record = app.db.consume_gateway_ticket(ticket.json()['ticket'])
        assert record and record['profile'] == 'default'
        assert app.db.consume_gateway_ticket(ticket.json()['ticket']) is None


def test_windows_scanner_command_parsing():
    from app.config import _split_command

    command = _split_command(
        '"C:\\Program Files\\Windows Defender\\MpCmdRun.exe" -Scan -ScanType 3 -File',
        windows=True,
    )
    assert command[0] == r"C:\Program Files\Windows Defender\MpCmdRun.exe"
    assert command[1:] == ("-Scan", "-ScanType", "3", "-File")


def test_refresh_cannot_rebind_to_a_new_device(test_settings):
    with client(test_settings) as api:
        first = login(api, device_id="original-device", device_name="Original")
        rotated = api.post("/api/auth/refresh", json={
            "refresh_token": first["refresh_token"],
            "device_id": "attacker-selected-device",
            "device_name": "Renamed",
        })
        assert rotated.status_code == 200
        assert rotated.json()["device_id"] == "original-device"


def test_gateway_blocks_slash_bypass_and_raw_attachments(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        app = api.app.state.companion
        user = app.db.resolve_token(tokens["access_token"])
        slash = _validate_client_frame(app, user, "default", json.dumps({
            "jsonrpc": "2.0", "id": 9, "method": "prompt.submit",
            "params": {"text": "/terminal rm -rf build"},
        }), set())
        assert json.loads(slash)["error"]["code"] == 4032

        raw = _validate_client_frame(app, user, "default", json.dumps({
            "jsonrpc": "2.0", "id": 10, "method": "image.attach_bytes",
            "params": {"content_base64": "AA=="},
        }), set())
        assert json.loads(raw)["error"]["code"] == -32601

        create = _validate_client_frame(app, user, "default", json.dumps({
            "jsonrpc": "2.0", "id": 11, "method": "session.create",
            "params": {"cwd": "C:\\sensitive", "title": "safe"},
        }), set())
        assert "cwd" not in json.loads(create)["params"]


def test_overview_reports_attention_counts(test_settings):
    with client(test_settings) as api:
        tokens = login(api)
        headers = auth(tokens)
        payload = api.get('/api/overview', headers=headers).json()
        assert 'attention' in payload
        assert set(payload['attention']) >= {'unread', 'approvals'}
        assert payload['attention']['approvals'] == 0
