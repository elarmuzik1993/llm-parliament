"""Precedence rules for the --hansard / env / config / default level toggle."""

from __future__ import annotations

import pytest

from parliament.config import resolve_hansard_level
from parliament.render.hansard import HansardLevel


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)


def test_default_is_minimal_when_nothing_set():
    assert resolve_hansard_level(cli_flag=None, config={}) is HansardLevel.MINIMAL


def test_cli_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "minimal")
    assert resolve_hansard_level(cli_flag="full", config={}) is HansardLevel.FULL


def test_cli_flag_wins_over_config():
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag="minimal", config=cfg) is HansardLevel.MINIMAL


def test_env_wins_over_config_when_cli_unset(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "full")
    cfg = {"hansard": {"level": "minimal"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.FULL


def test_config_used_when_cli_and_env_unset():
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.ARCHIVE


def test_missing_hansard_section_falls_back_to_default():
    assert resolve_hansard_level(cli_flag=None, config={"parliament": {}}) is HansardLevel.MINIMAL


def test_hansard_present_but_level_missing_falls_back_to_default():
    assert resolve_hansard_level(cli_flag=None, config={"hansard": {}}) is HansardLevel.MINIMAL


@pytest.mark.parametrize("env_val,expected", [
    ("minimal", HansardLevel.MINIMAL),
    ("VERDICT", HansardLevel.VERDICT),
    ("  archive  ", HansardLevel.ARCHIVE),
    ("Full", HansardLevel.FULL),
])
def test_env_normalization(monkeypatch, env_val, expected):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", env_val)
    assert resolve_hansard_level(cli_flag=None, config={}) is expected


def test_invalid_cli_flag_falls_back_to_default():
    """Unknown CLI value is normalized via HansardLevel.parse, which falls back to MINIMAL."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert resolve_hansard_level(cli_flag="nonsense", config={}) is HansardLevel.MINIMAL


def test_yaml_string_value_works(monkeypatch):
    """YAML naturally parses 'archive' as a string; helper must accept that."""
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.ARCHIVE
