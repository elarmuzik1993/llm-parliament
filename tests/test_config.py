"""Config loading — first-run copy and explicit-path behavior."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def fresh_home(tmp_path, monkeypatch):
    """Point ~/.parliament at a clean temp dir and reload parliament.config."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import parliament.config as config

    importlib.reload(config)
    return config, tmp_path


def test_first_run_copies_example_to_user_config(fresh_home):
    config, home = fresh_home

    assert not config.USER_CONFIG.exists()

    cfg = config.load_config()

    assert config.USER_CONFIG.exists()
    assert config.USER_CONFIG.parent == home / ".parliament"
    names = [m["name"] for m in cfg["parliament"]["members"]]
    assert names == ["Mock-A", "Mock-B", "Mock-C"]


def test_second_run_does_not_overwrite_user_config(fresh_home):
    config, _ = fresh_home

    config.load_config()
    config.USER_CONFIG.write_text(
        "parliament:\n  name: Edited\n  members: []\nproviders: {}\n",
        encoding="utf-8",
    )

    cfg = config.load_config()

    assert cfg["parliament"]["name"] == "Edited"


def test_explicit_path_does_not_trigger_first_run(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import parliament.config as config

    importlib.reload(config)

    explicit = tmp_path / "custom.yaml"
    explicit.write_text(
        "parliament:\n  name: Custom\n  members: []\nproviders: {}\n",
        encoding="utf-8",
    )

    cfg = config.load_config(explicit)

    assert cfg["parliament"]["name"] == "Custom"
    assert not config.USER_CONFIG.exists()
