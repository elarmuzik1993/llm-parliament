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


def test_key_providers_maps_provider_names_to_env_vars():
    from parliament.config import KEY_PROVIDERS

    assert KEY_PROVIDERS["anthropic"] == "ANTHROPIC_API_KEY"
    assert KEY_PROVIDERS["openai"] == "OPENAI_API_KEY"
    assert KEY_PROVIDERS["google"] == "GOOGLE_API_KEY"


def test_api_key_status_returns_configured_when_env_set(monkeypatch):
    from parliament.config import api_key_status

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert api_key_status("anthropic") == "configured"


def test_api_key_status_returns_missing_when_env_unset(monkeypatch):
    from parliament.config import api_key_status

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert api_key_status("anthropic") == "missing"


def test_api_key_status_returns_not_required_for_unknown_provider():
    from parliament.config import api_key_status

    assert api_key_status("ollama") == "not required"
    assert api_key_status("mock") == "not required"


def test_example_config_carries_display_show_debate(fresh_home):
    """The bundled example config must surface display.show_debate so users discover the toggle."""
    config, _ = fresh_home

    cfg = config.load_config()

    assert "display" in cfg, (
        "config.example.yaml should include a `display` section to advertise --show-debate"
    )
    assert cfg["display"]["show_debate"] is True


def test_example_config_carries_hansard_level(fresh_home):
    """The bundled example must surface hansard.level so users discover the toggle."""
    config, _ = fresh_home
    cfg = config.load_config()
    assert cfg.get("hansard", {}).get("level") == "verdict"


def test_user_supplied_show_debate_false_round_trips(tmp_path, monkeypatch):
    """A user who writes show_debate: false in their YAML must see it preserved on load."""
    monkeypatch.setattr(__import__("pathlib").Path, "home", lambda: tmp_path)
    import parliament.config as config
    import importlib
    importlib.reload(config)

    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "parliament:\n"
        "  name: Test\n"
        "  members:\n"
        "    - name: A\n"
        "      provider: mock\n"
        "      model: mock-v1\n"
        "    - name: B\n"
        "      provider: mock\n"
        "      model: mock-v2\n"
        "providers: {}\n"
        "display:\n"
        "  show_debate: false\n",
        encoding="utf-8",
    )

    cfg = config.load_config(custom)

    assert cfg["display"]["show_debate"] is False
    assert config.resolve_show_debate(cli_flag=None, config=cfg) is False
