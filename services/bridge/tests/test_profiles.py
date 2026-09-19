import pytest

from app.config import ProfileSpec, is_hard_blocked_profile


def test_safety_world_names_are_hard_blocked():
    for name in ["live-safe", "live_judge", "HermesSafety", "safety world", "safety-world"]:
        assert is_hard_blocked_profile(name)


def test_safety_profile_cannot_load():
    with pytest.raises(ValueError):
        ProfileSpec.from_dict(
            {
                "slug": "live-safe",
                "route_prefix": "/p/live-safe",
                "api_key_env": "X",
            }
        )


def test_named_profile_prefix_must_match_slug():
    with pytest.raises(ValueError):
        ProfileSpec.from_dict(
            {
                "slug": "mentos",
                "route_prefix": "/p/default",
                "api_key_env": "X",
            }
        )



def test_api_key_environment_name_is_validated():
    with pytest.raises(ValueError):
        ProfileSpec.from_dict(
            {
                "slug": "mentos",
                "route_prefix": "/p/mentos",
                "api_key_env": "../../not-an-env-name",
            }
        )
