def test_nav_uses_plain_words(phone):
    text = phone.locator(".app-shell").inner_text()
    for jargon in ("Command Center", "Live Gateway", "Durable", "Regular Hermes"):
        assert jargon not in text, jargon


def test_profile_slugs_hidden_on_home(phone):
    from conftest import PROFILES
    home = phone.locator(".page").inner_text()
    for slug in [s for s in PROFILES if s != "default" and "-" in s][:3]:
        assert slug not in home, slug
