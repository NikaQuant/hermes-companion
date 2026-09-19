def test_rename_uses_in_app_dialog_not_prompt(phone):
    phone.add_init_script(
        "window.prompt = () => { throw new Error('native prompt used') };"
        "window.confirm = () => { throw new Error('native confirm used') }"
    )
    phone.reload(wait_until="networkidle")
    phone.locator(".app-shell").wait_for(timeout=20_000)
    phone.locator('nav.tabbar a[data-nav="/chat"]').first.click()
    phone.wait_for_timeout(800)
    toggle = phone.locator('[data-action="chat-drawer-open"]')
    if toggle.count():
        toggle.first.click()
        phone.wait_for_timeout(300)
    phone.locator('[data-action="quick-new-session"]').click()
    dialog = phone.locator("dialog.sheet[open]")
    dialog.wait_for(timeout=5_000)
    assert dialog.is_visible()
    assert dialog.locator("input, textarea, select").count() >= 1
    dialog.locator('button[value="cancel"]').click()
    assert phone.locator("dialog.sheet[open]").count() == 0
