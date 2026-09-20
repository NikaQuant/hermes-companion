from __future__ import annotations

import os
import shutil
from pathlib import Path

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError as exc:  # pragma: no cover - optional operator tooling
    raise SystemExit("Install Playwright first: pip install playwright && playwright install chromium") from exc

BASE_URL = os.getenv("COMPANION_E2E_URL", "http://127.0.0.1:8787").rstrip("/")
EMAIL = os.getenv("COMPANION_E2E_EMAIL", "")
PASSWORD = os.getenv("COMPANION_E2E_PASSWORD", "")
SCREENSHOTS = Path(os.getenv("COMPANION_E2E_SCREENSHOTS", "artifacts/e2e"))

if not EMAIL or not PASSWORD:
    raise SystemExit("Set COMPANION_E2E_EMAIL and COMPANION_E2E_PASSWORD")

SCREENSHOTS.mkdir(parents=True, exist_ok=True)
errors: list[str] = []


def attach_error_capture(page: Page) -> None:
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("requestfailed", lambda request: errors.append(f"requestfailed: {request.method} {request.url} {request.failure}"))


def login(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator('input[name="email"]').fill(EMAIL)
    page.locator('input[name="password"]').fill(PASSWORD)
    page.locator('button[type="submit"]').click()
    page.get_by_role("heading", name="Home", exact=True).wait_for(timeout=20_000)


def click_nav(page: Page, path: str) -> None:
    page.locator(f'[data-nav="{path}"]:visible').first.click()


def navigate(page: Page, path: str, heading: str) -> None:
    click_nav(page, path)
    page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=20_000)


def fill_sheet(page: Page, value: str) -> None:
    sheet = page.locator("dialog.sheet")
    sheet.wait_for(timeout=10_000)
    field = sheet.locator("input, textarea").first
    field.fill(value)
    sheet.locator('button[type="submit"]').click()
    sheet.wait_for(state="detached", timeout=10_000)


with sync_playwright() as playwright:
    executable = os.getenv("PLAYWRIGHT_CHROMIUM") or shutil.which("chromium") or shutil.which("google-chrome")
    launch_options: dict[str, object] = {"headless": True}
    if executable:
        launch_options["executable_path"] = executable
    browser = playwright.chromium.launch(**launch_options)

    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    attach_error_capture(page)
    login(page)

    page.locator(".assistant-card").first.wait_for()
    page.locator(".assistant-card .status-pill.online").first.wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "command-center.png"), full_page=True)

    navigate(page, "/projects", "Projects")
    page.locator(".project-card").first.wait_for(timeout=20_000)
    assert page.locator(".project-card").count() >= 1
    page.screenshot(path=str(SCREENSHOTS / "projects.png"), full_page=True)

    navigate(page, "/sessions", "Conversations")
    page.get_by_text("Hermes Companion Demo", exact=True).wait_for(timeout=20_000)
    page.locator('[data-action="session-menu"]').first.click()
    page.locator(".sheet-list button").filter(has_text="Pin to top").click()
    page.locator("article.session-card.pinned").first.wait_for(timeout=10_000)
    page.screenshot(path=str(SCREENSHOTS / "sessions.png"), full_page=True)

    page.locator(".session-card-main").first.click()
    page.locator(".chat-title strong").get_by_text("Hermes Companion Demo", exact=True).wait_for(timeout=20_000)
    page.get_by_text("The bridge keeps Hermes keys server-side", exact=False).wait_for(timeout=20_000)
    composer = page.locator("#composer-form textarea")
    composer.fill("Confirm that this client is connected.")
    page.locator("#composer-form button[type=submit]").click()
    page.get_by_text("Hermes Companion is connected successfully.", exact=True).wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "chat-run.png"), full_page=True)

    navigate(page, "/notifications", "Alerts")
    page.get_by_role("heading", name="Alerts", exact=True).wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "notifications.png"), full_page=True)

    navigate(page, "/prompts", "Saved prompts")
    page.locator('#prompt-create-form input[name="title"]').fill("E2E review")
    page.locator('#prompt-create-form textarea[name="prompt"]').fill("Review the current Hermes project state and list concrete next actions.")
    page.locator('#prompt-create-form button[type="submit"]').click()
    page.get_by_text("E2E review", exact=True).wait_for(timeout=10_000)
    page.locator('[data-action="prompt-use"]').first.click()
    page.locator("#composer-form textarea").wait_for(timeout=20_000)
    assert "Review the current Hermes project state" in page.locator("#composer-form textarea").input_value()

    navigate(page, "/files", "Files")
    upload_name = "hermes-companion-e2e.txt"
    page.locator('#file-upload-form input[type="file"]').set_input_files({
        "name": upload_name,
        "mimeType": "text/plain",
        "buffer": b"Hermes Companion E2E staged file.\n",
    })
    page.get_by_text(upload_name, exact=True).wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "files.png"), full_page=True)

    navigate(page, "/admin", "Users")
    page.locator('[data-action="diagnostics-refresh"]').click()
    page.locator(".diagnostic-output").wait_for(timeout=20_000)
    page.locator('[data-action="backup-create"]').click()
    fill_sheet(page, "e2e")
    page.locator(".backup-row").first.wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "administration.png"), full_page=True)

    navigate(page, "/settings", "Settings")
    page.locator(".device-row").first.wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "settings.png"), full_page=True)

    navigate(page, "/audit", "Activity log")
    page.locator(".audit-row").first.wait_for(timeout=20_000)
    page.screenshot(path=str(SCREENSHOTS / "audit.png"), full_page=True)
    context.close()

    mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True)
    mobile_page = mobile.new_page()
    attach_error_capture(mobile_page)
    login(mobile_page)
    mobile_page.screenshot(path=str(SCREENSHOTS / "mobile-command-center.png"), full_page=True)
    mobile_page.locator('.tabbar [data-nav="/chat"]:visible').click()
    mobile_page.locator("#composer-form textarea").wait_for(timeout=20_000)
    mobile_page.get_by_text("The bridge keeps Hermes keys server-side", exact=False).wait_for(timeout=20_000)
    mobile_page.screenshot(path=str(SCREENSHOTS / "mobile-chat.png"), full_page=True)
    mobile.close()
    browser.close()

if errors:
    unique = list(dict.fromkeys(errors))
    raise SystemExit("Browser errors:\n" + "\n".join(unique))
print("Hermes Companion browser control-plane smoke test passed")
