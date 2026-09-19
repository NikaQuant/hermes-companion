from __future__ import annotations

import pathlib
import secrets
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "bridge"))
from app.db import Database  # noqa: E402

BASE_URL = "http://127.0.0.1:8787"
EMAIL = "ui-e2e@hermescompanion.dev"


def _profiles() -> list[str]:
    import json
    try:
        data = json.loads((ROOT / "config" / "profiles.json").read_text(encoding="utf-8"))
        return [p["slug"] for p in data.get("profiles", [])] or ["default"]
    except (OSError, ValueError, KeyError):
        return ["default"]


PROFILES = _profiles()


@pytest.fixture(scope="session")
def account():
    db = Database(ROOT / "services" / "bridge" / "data" / "hermes_companion.db")
    existing = db.get_user_by_email(EMAIL)
    if existing:
        db.delete_user(existing["id"])
    password = secrets.token_urlsafe(24)
    user = db.create_user(email=EMAIL, password=password, role="admin", active=True, profiles=PROFILES)
    yield {"email": EMAIL, "password": password, "id": user["id"]}
    try:
        db.delete_user(user["id"])
    except Exception:
        pass


def _login(page, account):
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator('input[name="email"]').fill(account["email"])
    page.locator('input[name="password"]').fill(account["password"])
    page.locator('#login-form button[type="submit"]').click()
    page.locator(".app-shell").wait_for(timeout=20_000)


@pytest.fixture
def phone(browser, account):
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=3,
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    _login(page, account)
    yield page
    context.close()


@pytest.fixture
def desktop(browser, account):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    _login(page, account)
    yield page
    context.close()


def open_more(page, path: str):
    page.locator("nav.tabbar a[data-more]").click()
    sheet = page.locator("dialog.sheet[open]")
    sheet.wait_for(timeout=5_000)
    sheet.locator(f'.sheet-list button[data-value="{path}"]').click()
