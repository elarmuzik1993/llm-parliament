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


def test_check_provider_returns_both_ok_when_sdk_imports_and_key_set(monkeypatch):
    from parliament import doctor

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sdk_result, key_result = doctor._check_provider("anthropic")

    assert sdk_result.ok is True
    assert "Anthropic SDK" in sdk_result.message
    assert key_result.ok is True
    assert key_result.info is False
    assert "configured" in key_result.message


def test_check_provider_returns_info_when_key_missing(monkeypatch):
    from parliament import doctor

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, key_result = doctor._check_provider("anthropic")

    assert key_result.ok is True
    assert key_result.info is True
    assert "not set" in key_result.message


def test_check_provider_fails_when_sdk_unimportable(monkeypatch):
    from parliament import doctor

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    sdk_result, _ = doctor._check_provider("anthropic")

    assert sdk_result.ok is False
    assert "SDK" in sdk_result.message


def test_check_ollama_reports_reachable_with_model_count(monkeypatch):
    from parliament import doctor
    import httpx

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"models": [{"name": "llama3.1:latest"}, {"name": "deepseek-r1:8b"}]}

    def fake_get(url, timeout=None):
        assert "11434" in url
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True
    assert result.info is False
    assert "2 model" in result.message  # "2 models" or "2 model(s)"


def test_check_ollama_reports_unreachable_as_info_not_failure(monkeypatch):
    from parliament import doctor
    import httpx

    def fake_get(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True
    assert result.info is True
    assert "not reachable" in result.message


def test_check_ollama_treats_timeout_as_unreachable(monkeypatch):
    from parliament import doctor
    import httpx

    def fake_get(url, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True
    assert result.info is True


def test_doctor_exit_code_is_one_when_python_too_old(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.version_info", (3, 10, 4, "final", 0))

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 1
    assert "not functional" in result.output.lower() or "fix" in result.output.lower()


def test_doctor_exit_code_is_zero_when_only_optional_items_missing(monkeypatch, tmp_path):
    """No keys, no Ollama -> still exit 0 (mock works fine)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    import httpx

    def unreachable(url, timeout=None):
        raise httpx.ConnectError("no ollama")

    monkeypatch.setattr(httpx, "get", unreachable)

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0


def test_doctor_next_steps_mentions_keys_and_ollama_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    import httpx

    def unreachable(url, timeout=None):
        raise httpx.ConnectError("no ollama")

    monkeypatch.setattr(httpx, "get", unreachable)

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert "parliament keys set" in result.output
    assert "ollama" in result.output.lower()
