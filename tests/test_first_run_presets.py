"""Tests for first-run preset selection."""

from __future__ import annotations

from dataclasses import replace

from parliament.first_run import Environment
from parliament.model_catalog import OllamaModel
from parliament.presets import select_preset


BASE_ENV = Environment(
    anthropic_key=False,
    openai_key=False,
    google_key=False,
    ollama_reachable=False,
    ollama_models=(),
    total_ram_bytes=16 * 1024**3,
)


def _members(preset):
    return [
        (m["name"], m["provider"], m["model"])
        for m in preset.config["parliament"]["members"]
    ]


def test_anthropic_key_selects_cloud_anthropic() -> None:
    preset = select_preset(replace(BASE_ENV, anthropic_key=True))

    assert preset.name == "cloud-anthropic"
    assert [provider for _, provider, _ in _members(preset)] == [
        "anthropic",
        "anthropic",
        "anthropic",
    ]
    assert preset.config["display"]["show_debate"] is True
    assert preset.config["hansard"]["level"] == "verdict"


def test_single_cloud_key_plus_two_fit_local_models_selects_mixed() -> None:
    env = replace(
        BASE_ENV,
        openai_key=True,
        ollama_reachable=True,
        ollama_models=(
            OllamaModel("big:latest", 20 * 1024**3),
            OllamaModel("tiny", 1 * 1024**3),
            OllamaModel("small", 2 * 1024**3),
        ),
    )

    preset = select_preset(env)

    assert preset.name == "mixed"
    assert _members(preset) == [
        ("GPT", "openai", "gpt-4o"),
        ("Tiny", "ollama", "tiny"),
        ("Small", "ollama", "small"),
    ]


def test_local_safe_uses_three_smallest_models_that_fit_ram() -> None:
    env = replace(
        BASE_ENV,
        ollama_reachable=True,
        ollama_models=(
            OllamaModel("huge", 30 * 1024**3),
            OllamaModel("b", 2 * 1024**3),
            OllamaModel("a", 1 * 1024**3),
            OllamaModel("c", 3 * 1024**3),
        ),
    )

    preset = select_preset(env)

    assert preset.name == "local-safe"
    assert [model for _, _, model in _members(preset)] == ["a", "b", "c"]


def test_local_models_route_to_hint_when_three_smallest_exceed_ram() -> None:
    env = replace(
        BASE_ENV,
        ollama_reachable=True,
        ollama_models=(
            OllamaModel("a", 8 * 1024**3),
            OllamaModel("b", 8 * 1024**3),
            OllamaModel("c", 8 * 1024**3),
        ),
    )

    preset = select_preset(env)

    assert preset.name == "mock-ollama-hint"
    assert [provider for _, provider, _ in _members(preset)] == ["mock", "mock", "mock"]


def test_all_cloud_keys_selects_cloud_full_with_current_google_default() -> None:
    preset = select_preset(
        replace(BASE_ENV, anthropic_key=True, openai_key=True, google_key=True)
    )

    assert preset.name == "cloud-full"
    assert _members(preset) == [
        ("Claude", "anthropic", "claude-sonnet-4-6"),
        ("GPT-Mini", "openai", "gpt-4o-mini"),
        ("Gemini", "google", "gemini-2.5-flash"),
    ]
