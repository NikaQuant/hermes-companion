from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"test_{name.replace('-', '_')}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restore_rejects_cross_platform_path_traversal():
    restore = load_script("restore-backup.py")
    for name in ("../secret", "..\\secret", "/absolute", "C:\\absolute"):
        with pytest.raises(ValueError):
            restore._validate_member(name)


def test_release_packager_excludes_secret_file_types(tmp_path: Path):
    packager = load_script("build-release.py")
    assert packager.should_skip(Path(".env"))
    assert packager.should_skip(Path("keys/release.pfx"))
    assert packager.should_skip(Path("services/bridge/data/live.db"))
    assert not packager.should_skip(Path("docs/SECURITY.md"))
