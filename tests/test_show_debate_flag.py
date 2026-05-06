"""Precedence rules for the --show-debate / env / config / default toggle."""

from __future__ import annotations

import pytest

from parliament.config import resolve_show_debate


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with PARLIAMENT_SHOW_DEBATE unset."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)


def test_default_is_on_when_nothing_set():
    assert resolve_show_debate(cli_flag=None, config={}) is True


def test_cli_true_wins_over_env_off():
    import os
    os.environ["PARLIAMENT_SHOW_DEBATE"] = "0"
    try:
        assert resolve_show_debate(cli_flag=True, config={"display": {"show_debate": False}}) is True
    finally:
        del os.environ["PARLIAMENT_SHOW_DEBATE"]


def test_cli_false_wins_over_env_on():
    import os
    os.environ["PARLIAMENT_SHOW_DEBATE"] = "1"
    try:
        assert resolve_show_debate(cli_flag=False, config={"display": {"show_debate": True}}) is False
    finally:
        del os.environ["PARLIAMENT_SHOW_DEBATE"]


def test_env_wins_over_config_when_cli_unset(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")
    assert resolve_show_debate(cli_flag=None, config={"display": {"show_debate": True}}) is False


def test_config_used_when_cli_and_env_unset():
    assert resolve_show_debate(cli_flag=None, config={"display": {"show_debate": False}}) is False


@pytest.mark.parametrize("env_val,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True),
    ("on", True), ("ON", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False),  # explicit empty -> off
])
def test_env_truthy_strings(monkeypatch, env_val, expected):
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", env_val)
    assert resolve_show_debate(cli_flag=None, config={}) is expected


def test_missing_display_section_falls_back_to_default():
    """Config without a 'display' key still defaults ON."""
    assert resolve_show_debate(cli_flag=None, config={"parliament": {}}) is True


def test_display_present_but_show_debate_missing_falls_back_to_default():
    """display: {} (no show_debate key) defaults ON."""
    assert resolve_show_debate(cli_flag=None, config={"display": {}}) is True
