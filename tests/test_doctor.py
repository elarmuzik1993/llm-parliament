"""Health-check command tests."""

from __future__ import annotations

import builtins
import importlib
import os
import sys
from pathlib import Path

from click.testing import CliRunner


def test_doctor_command_runs_and_exits_zero_on_a_working_install(monkeypatch, tmp_path):
    """Bare smoke test: `parliament doctor` runs without crashing on a healthy box."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from parliament import cli

    result = CliRunner().invoke(cli.main, ["doctor"])

    # Skeleton phase: the command exists and exits 0 when there's nothing wrong.
    assert result.exit_code == 0, result.output
    assert "Environment" in result.output or "Doctor" in result.output


def test_check_python_version_passes_on_supported_version(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr("sys.version_info", (3, 12, 5, "final", 0))
    result = doctor._check_python_version()

    assert result.ok is True
    assert "3.12.5" in result.message


def test_check_python_version_fails_on_too_old(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr("sys.version_info", (3, 10, 4, "final", 0))
    result = doctor._check_python_version()

    assert result.ok is False
    assert "3.10.4" in result.message
    assert ">=3.11" in result.message or "3.11" in result.message


def test_check_curses_passes_when_curses_imports():
    from parliament import doctor

    result = doctor._check_curses()
    assert result.ok is True


def test_check_curses_fails_when_curses_unimportable(monkeypatch):
    from parliament import doctor
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "curses":
            raise ImportError("no curses on this box")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "curses", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = doctor._check_curses()
    assert result.ok is False


def test_check_terminal_size_passes_on_large_enough(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr(os, "get_terminal_size", lambda *_: os.terminal_size((142, 38)))
    result = doctor._check_terminal_size()

    assert result.ok is True
    assert "142" in result.message
    assert "38" in result.message


def test_check_terminal_size_warns_when_too_small(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr(os, "get_terminal_size", lambda *_: os.terminal_size((60, 20)))
    result = doctor._check_terminal_size()

    assert result.ok is True
    assert result.warn is True


def test_check_config_passes_after_first_run(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import parliament.config

    importlib.reload(parliament.config)
    from parliament import doctor

    result = doctor._check_config()
    assert result.ok is True
    assert "config.yaml" in result.message
