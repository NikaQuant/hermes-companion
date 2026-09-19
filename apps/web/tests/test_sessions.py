def test_sessions_are_cards_on_phone(phone):
    phone.locator('nav.tabbar a[data-nav="/sessions"]').click()
    phone.get_by_role("heading", name="Conversations").wait_for(timeout=10_000)
    phone.locator(".panel-loader").wait_for(state="detached", timeout=20_000)
    assert phone.locator("table.session-table").count() == 0
    cards = phone.locator(".session-card")
    if cards.count() == 0:
        assert phone.locator(".empty-state").count() >= 1
        return
    cards.first.locator("[data-action='session-menu']").click()
    assert phone.locator("dialog.sheet[open]").is_visible()
