def test_home_shows_attention_and_recent(phone):
    phone.locator('nav.tabbar a[data-nav="/"]').click()
    page = phone.locator(".page")
    page.get_by_text("Needs your attention").wait_for(timeout=10_000)
    page.get_by_text("Recent conversations", exact=True).wait_for(timeout=10_000)
    assert page.get_by_text("Recent conversations", exact=True).count() == 1
    assert phone.locator(".assistant-card").count() >= 4
    assert "Attached run" not in page.inner_text()


def test_first_run_checklist_shows_until_dismissed(phone):
    phone.evaluate("localStorage.removeItem('hermes.companion.hc.checklistDismissed')")
    phone.reload(wait_until="networkidle")
    phone.locator(".app-shell").wait_for(timeout=20_000)
    card = phone.locator(".checklist")
    card.wait_for(timeout=10_000)
    for step in ("Add to home screen", "Turn on alerts", "Add a passkey"):
        assert card.get_by_text(step, exact=True).count() == 1
    card.locator('[data-action="checklist-dismiss"]').click()
    assert phone.locator(".checklist").count() == 0
    phone.reload(wait_until="networkidle")
    phone.locator(".app-shell").wait_for(timeout=20_000)
    assert phone.locator(".checklist").count() == 0
