"""Tests for first-run preset selection."""

from __future__ import annotations

from dataclasses import asdict, replace
from itertools import product
from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize("keys", list(product([False, True], repeat=3)))
@pytest.mark.parametrize("local", [False, True])
def test_openrouter_precedence_and_model_diversity(keys: tuple[bool, ...], local: bool) -> None:
    env = SimpleNamespace(**{**asdict(BASE_ENV), "openrouter_key": True})
    env.anthropic_key, env.openai_key, env.google_key = keys
    if local:
        env.ollama_reachable = True
        env.ollama_models = tuple(OllamaModel(name, 1) for name in ["a", "b", "c"])
    preset = select_preset(env)

    if all(keys):
        assert preset.name == "cloud-full"
    else:
        assert preset.name == "cloud-openrouter"
        members = preset.config["parliament"]["members"]
        assert len(members) == 3
        assert {member["provider"] for member in members} == {"openrouter"}
        assert {member["model"].split("/")[0] for member in members} == {
            "anthropic", "openai", "google",
        }
        assert preset.config["hansard"]["level"] == "verdict"
