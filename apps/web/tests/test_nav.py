def test_bottom_tabs_on_phone(phone):
    tabs = phone.locator("nav.tabbar a")
    assert tabs.count() == 5
    labels = [t.inner_text().strip().split("\n")[-1] for t in tabs.all()]
    assert labels == ["Home", "Chat", "Conversations", "Alerts", "More"]
    tabs.nth(3).click()
    phone.get_by_role("heading", name="Alerts").wait_for(timeout=10_000)


def test_more_opens_sheet_with_remaining_pages(phone):
    phone.locator("nav.tabbar a[data-more]").click()
    sheet = phone.locator("dialog.sheet[open]")
    assert sheet.is_visible()
    # tappable rows, not a <select>
    assert sheet.locator("select").count() == 0
    rows = sheet.locator(".sheet-list button")
    joined = " ".join(rows.all_inner_texts())
    for label in ("Scheduled tasks", "Files", "Saved prompts", "Live session", "Settings", "Sign out"):
        assert label in joined, label
    sizes = phone.evaluate("[...document.querySelectorAll('dialog.sheet .sheet-list button')].map(b => b.getBoundingClientRect().height)")
    assert min(sizes) >= 44, sizes
    rows.filter(has_text="Settings").click()
    phone.get_by_role("heading", name="Settings").wait_for(timeout=10_000)


def test_version_stamp_visible_on_phone(phone):
    badge = phone.locator(".mobile-header .brand-version")
    assert badge.is_visible()
    text = badge.inner_text().strip()
    assert text.startswith("v0.3.2 · ")
    assert not text.endswith("dev"), text  # build hash must be injected by build-web.py


def test_no_tabbar_on_desktop(desktop):
    assert desktop.locator("nav.tabbar").count() == 0 or not desktop.locator("nav.tabbar").is_visible()


def test_assistant_switcher_lists_labels_not_slugs(phone):
    import json
    from conftest import ROOT
    profiles = json.loads((ROOT / "config" / "profiles.json").read_text(encoding="utf-8"))["profiles"]
    options = phone.locator(".mobile-header select.profile-picker-native option").all_inner_texts()
    joined = " ".join(options)
    for item in profiles:
        assert item["label"] in joined, item["label"]
        if item["slug"] != item["label"].lower():
            assert item["slug"] not in joined, item["slug"]
