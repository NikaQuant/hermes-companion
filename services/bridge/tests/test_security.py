from app.security import hash_password, stable_session_key, verify_password


def test_password_roundtrip():
    encoded = hash_password("a-secure-password-123")
    assert verify_password("a-secure-password-123", encoded)
    assert not verify_password("wrong-password", encoded)


def test_session_key_is_stable_and_profile_scoped():
    first = stable_session_key("secret", "user", "default")
    assert first == stable_session_key("secret", "user", "default")
    assert first != stable_session_key("secret", "user", "mentos")
