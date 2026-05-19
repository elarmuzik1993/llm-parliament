"""Tests for the first-run config wizard."""

from __future__ import annotations

import io

import yaml

from parliament.first_run import Environment, run_first_run_wizard
from parliament.model_catalog import OllamaModel


class _TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


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
