"""Tests for the first-run config wizard."""

from __future__ import annotations

import io

import pytest
import yaml

from parliament.first_run import Environment, run_first_run_wizard
from parliament.model_catalog import OllamaModel


@pytest.mark.parametrize("key", [None, "", "openrouter-test-key"])
def test_detects_openrouter_key(monkeypatch, key: str | None) -> None:
    from parliament.first_run import detect_environment
    from parliament.model_catalog import PickerData

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    if key is not None:
        monkeypatch.setenv("OPENROUTER_API_KEY", key)
    monkeypatch.setattr(
        "parliament.first_run.fetch_ollama_models",
        lambda *args, **kwargs: PickerData(models=[], notice="not reachable"),
    )
    assert detect_environment().openrouter_key is bool(key)


class _TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize("interactive", [False, True])
def test_openrouter_wizard_writes_usable_config_without_key(monkeypatch, tmp_path, interactive) -> None:
    from parliament.config import build_parliament_from_config
    from parliament.model_catalog import PickerData

    for name in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")
    monkeypatch.setattr(
        "parliament.first_run.fetch_ollama_models",
        lambda *args, **kwargs: PickerData(models=[], notice="not reachable"),
    )
    output = _TTYOutput() if interactive else io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    monkeypatch.setattr("sys.stdin", _TTYInput("y\n") if interactive else io.StringIO())

    path = tmp_path / "config.yaml"
    preset = run_first_run_wizard(path)
    saved = path.read_text(encoding="utf-8")
    assert preset.name == "cloud-openrouter"
    assert "openrouter-test-key" not in saved
    assert "openrouter-test-key" not in output.getvalue()
    members, providers = build_parliament_from_config(yaml.safe_load(saved))
    assert len(members) == len(providers) == 3
    for provider in providers.values():
        assert provider._base_url == "https://openrouter.ai/api/v1"
        assert provider._api_key == "openrouter-test-key"
    if interactive:
        assert "OPENROUTER_API_KEY" in output.getvalue()
        assert "cloud-openrouter" in output.getvalue()


def test_non_tty_writes_detected_preset(monkeypatch, tmp_path) -> None:
    env = Environment(
        anthropic_key=True,
        openai_key=False,
        google_key=False,
        ollama_reachable=False,
        ollama_models=(),
        total_ram_bytes=16 * 1024**3,
    )
    monkeypatch.setattr("parliament.first_run.detect_environment", lambda: env)

    path = tmp_path / "config.yaml"
    preset = run_first_run_wizard(path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert preset.name == "cloud-anthropic"
    assert cfg["parliament"]["members"][0]["provider"] == "anthropic"


def test_tty_no_writes_mock_preset(monkeypatch, tmp_path) -> None:
    env = Environment(
        anthropic_key=True,
        openai_key=False,
        google_key=False,
        ollama_reachable=True,
        ollama_models=(OllamaModel("tiny", 1), OllamaModel("small", 2)),
        total_ram_bytes=16 * 1024**3,
    )
    monkeypatch.setattr("parliament.first_run.detect_environment", lambda: env)
    monkeypatch.setattr("sys.stdin", _TTYInput("n\n"))
    monkeypatch.setattr("sys.stdout", _TTYOutput())

    path = tmp_path / "config.yaml"
    preset = run_first_run_wizard(path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert preset.name == "mock"
    assert [m["provider"] for m in cfg["parliament"]["members"]] == ["mock", "mock", "mock"]
