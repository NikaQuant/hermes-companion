from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Test modules import ``app.main`` during collection. That module exposes the
# production ASGI object and therefore initializes its configured database at
# import time. Point that collection-time instance at a disposable directory
# before importing any application module so a plain ``pytest`` run can never
# create runtime state inside the release tree.
_COLLECTION_ROOT = Path(tempfile.mkdtemp(prefix="hermes-companion-pytest-"))
os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET"] = "collection-test-secret-" + "x" * 32
os.environ["DATABASE_PATH"] = str(_COLLECTION_ROOT / "collection.db")
os.environ["WEB_DIST_DIR"] = str(_COLLECTION_ROOT / "dist")
os.environ["UPLOAD_ROOT"] = str(_COLLECTION_ROOT / "uploads")
os.environ["BACKUP_ROOT"] = str(_COLLECTION_ROOT / "backups")

from app.config import Settings


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    shutil.rmtree(_COLLECTION_ROOT, ignore_errors=True)


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    profiles = {
        "profiles": [
            {
                "slug": "default",
                "label": "Hermes Core",
                "description": "test",
                "route_prefix": "",
                "api_key_env": "HERMES_API_KEY_DEFAULT",
                "permissions": {
                    "read": True,
                    "chat": True,
                    "session_write": True,
                    "run_control": True,
                    "approval": True,
                    "jobs_write": True,
                    "files_write": True,
                    "gateway_live": True,
                },
            },
            {
                "slug": "mentos",
                "label": "Mentos",
                "description": "test",
                "route_prefix": "/p/mentos",
                "api_key_env": "HERMES_API_KEY_MENTOS",
                "permissions": {
                    "read": True,
                    "chat": True,
                    "session_write": True,
                    "run_control": True,
                    "approval": True,
                    "files_write": True,
                    "gateway_live": True,
                },
            },
        ]
    }
    (config_dir / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET", "x" * 48)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("HERMES_PROFILES_FILE", str(config_dir / "profiles.json"))
    monkeypatch.setenv("HERMES_BASE_URL", "http://hermes.test:8642")
    monkeypatch.setenv("HERMES_API_KEY_DEFAULT", "default-test-key")
    monkeypatch.setenv("HERMES_API_KEY_MENTOS", "mentos-test-key")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "nik@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "test-password-long-enough")
    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path / "dist"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setenv("HERMES_SERVE_URL", "http://127.0.0.1:9119")
    monkeypatch.setenv("HERMES_SERVE_SESSION_TOKEN", "serve-test-token-long-enough")
    return Settings.from_env(project_root=tmp_path, env_file=tmp_path / "missing.env")
