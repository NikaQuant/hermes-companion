def test_enter_key_submits_composer(phone):
    phone.locator('nav.tabbar a[data-nav="/chat"]').click()
    phone.wait_for_timeout(800)
    if phone.locator(".chat-empty").count():
        phone.locator('[data-action="quick-new-session"]').click()
        sheet = phone.locator("dialog.sheet[open]")
        if sheet.count():
            sheet.locator("input").fill("UX enter test")
            sheet.locator('button[type="submit"]').click()
        phone.locator("#composer-form textarea:not([disabled])").wait_for(timeout=20_000)
    textarea = phone.locator("#composer-form textarea")
    textarea.fill("Shift+Enter test")
    textarea.press("Shift+Enter")
    assert "\n" in textarea.input_value()
    phone.route("**/api/profiles/*/runs", lambda route: route.fulfill(json={"run_id": "ui-e2e-run", "status": "queued"}))
    textarea.fill("Say exactly OK and nothing else. Do not use tools.")
    textarea.press("Enter")
    phone.wait_for_timeout(1500)
    assert textarea.input_value() == ""


def test_chat_header_conversations_button(phone):
    phone.locator('nav.tabbar a[data-nav="/chat"]').click()
    phone.wait_for_timeout(800)
    assert phone.locator(".chat-drawer-toggle").inner_text().strip() == "Conversations"
