def test_offline_banner(phone):
    phone.context.set_offline(True)
    phone.wait_for_timeout(500)
    assert phone.locator(".offline-banner").is_visible()
    phone.context.set_offline(False)
    phone.wait_for_timeout(500)
    assert not phone.locator(".offline-banner").is_visible()
