def test_login_lands_on_shell(phone):
    assert phone.locator(".app-shell").is_visible()
