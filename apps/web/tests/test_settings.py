from conftest import open_more


def test_settings_sections_in_plain_order(phone):
    open_more(phone, "/settings")
    phone.get_by_role("heading", name="Settings").wait_for(timeout=10_000)
    headings = [h.strip() for h in phone.locator(".page h2").all_inner_texts()]
    assert headings[:4] == ["Sign-in", "Alerts", "This app", "Advanced"]
    assert "Safety World boundary" not in phone.locator(".page").inner_text()


def test_theme_toggle_persists(phone):
    phone.evaluate("localStorage.setItem('hermes.companion.hc.theme','light')")
    phone.reload(wait_until="networkidle")
    phone.locator(".app-shell").wait_for(timeout=20_000)
    assert phone.evaluate("document.documentElement.dataset.theme") == "light"
    bg = phone.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg != "rgb(9, 9, 11)"


def _luminance(rgb: str) -> float:
    nums = [float(x) for x in rgb.strip("rgba()").split(",")[:3]]
    return sum(nums) / 3


def test_light_theme_inputs_are_readable(phone):
    phone.evaluate("localStorage.setItem('hermes.companion.hc.theme','light')")
    phone.reload(wait_until="networkidle")
    phone.locator(".app-shell").wait_for(timeout=20_000)
    open_more(phone, "/settings")
    phone.get_by_role("heading", name="Settings").wait_for(timeout=10_000)
    styles = phone.evaluate(
        """(() => { const el = document.querySelector('#password-change-form input');
            const s = getComputedStyle(el); return { bg: s.backgroundColor, fg: s.color } })()"""
    )
    # text must contrast with its field: dark text on a light field
    assert _luminance(styles["bg"]) > 200, styles
    assert _luminance(styles["fg"]) < 80, styles
    phone.evaluate("localStorage.removeItem('hermes.companion.hc.theme')")


def test_sign_out_reachable_on_phone(phone):
    open_more(phone, "/settings")
    phone.get_by_role("heading", name="Settings").wait_for(timeout=10_000)
    assert phone.locator('.page [data-action="logout"]').count() == 1
    phone.locator("nav.tabbar a[data-more]").click()
    options = phone.locator("dialog.sheet[open] .sheet-list button").all_inner_texts()
    assert "Sign out" in [o.strip() for o in options]
    phone.locator('dialog.sheet[open] button[value="cancel"]').click()
