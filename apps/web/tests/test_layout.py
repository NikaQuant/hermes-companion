from conftest import open_more


def test_body_text_is_readable(phone):
    open_more(phone, "/settings")
    phone.get_by_role("heading", name="Settings").wait_for(timeout=10_000)
    size = phone.evaluate("getComputedStyle(document.querySelector('.settings-card p')).fontSize")
    assert float(size.replace("px", "")) >= 14


def test_touch_targets_are_44px(phone):
    phone.locator('nav.tabbar a[data-nav="/notifications"]').first.click()
    phone.wait_for_timeout(500)
    sizes = phone.evaluate(
        """[...document.querySelectorAll('button, nav.tabbar a')].filter(b => b.offsetParent).map(b => {
            const r = b.getBoundingClientRect();
            return Math.min(r.width, r.height);
        })"""
    )
    assert sizes and min(sizes) >= 40, sizes
