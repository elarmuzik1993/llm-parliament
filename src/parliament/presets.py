"""Environment-aware first-run config presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parliament.model_catalog import OllamaModel

CLAUDE_SONNET = "claude-sonnet-4-6"
CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
GPT_4O = "gpt-4o"
GPT_4O_MINI = "gpt-4o-mini"
GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"


@dataclass(frozen=True)
class Preset:
    name: str
    summary: str
    config: dict[str, Any]
    notice: str | None = None


def _base_config(members: list[dict[str, str]]) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    if any(m["provider"] == "ollama" for m in members):
        providers["ollama"] = {"base_url": "http://localhost:11434/v1"}
    return {
        "parliament": {
            "name": "House of AI",
            "members": members,
        },
        "providers": providers,
        "display": {"show_debate": True},
        "hansard": {"level": "minimal"},
    }


def _member(name: str, provider: str, model: str) -> dict[str, str]:
    return {"name": name, "provider": provider, "model": model}


def build_mock_preset(name: str = "mock", notice: str | None = None) -> Preset:
    return Preset(
        name=name,
        summary="mock parliament",
        config=_base_config(
            [
                _member("Mock-A", "mock", "mock-v1"),
                _member("Mock-B", "mock", "mock-v2"),
                _member("Mock-C", "mock", "mock-v3"),
            ]
        ),
        notice=notice,
    )


def _cloud_member(provider: str, slot: int = 1) -> dict[str, str]:
    if provider == "anthropic":
        names = ("Claude", "Claude-Haiku", "Claude-2")
        models = (CLAUDE_SONNET, CLAUDE_HAIKU, CLAUDE_SONNET)
    elif provider == "openai":
        names = ("GPT", "GPT-Mini", "GPT-2")
        models = (GPT_4O, GPT_4O_MINI, GPT_4O)
    elif provider == "google":
        names = ("Gemini", "Gemini-Lite", "Gemini-2")
        models = (GEMINI_FLASH, GEMINI_FLASH_LITE, GEMINI_FLASH)
    else:
        raise ValueError(f"Unknown cloud provider: {provider}")
    index = max(0, min(slot - 1, len(names) - 1))
    return _member(names[index], provider, models[index])


def _cloud_providers(env: Any) -> list[str]:
    providers: list[str] = []
    if env.anthropic_key:
        providers.append("anthropic")
    if env.openai_key:
        providers.append("openai")
    if env.google_key:
        providers.append("google")
    return providers


def _smallest_fit(
    models: tuple[OllamaModel, ...],
    count: int,
    total_ram_bytes: int | None,
) -> tuple[OllamaModel, ...]:
    sorted_models = tuple(sorted(models, key=lambda m: (m.size_bytes, m.name)))
    selected = sorted_models[:count]
    if len(selected) < count:
        return ()
    if total_ram_bytes is None:
        return selected
    limit = int(total_ram_bytes * 0.8)
    if sum(m.size_bytes for m in selected) <= limit:
        return selected
    return ()


def _ollama_members(models: tuple[OllamaModel, ...]) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    used: dict[str, int] = {}
    for model in models:
        base = model.name.split(":", 1)[0].replace("-", " ").replace("_", " ").title()
        name = "".join(part for part in base.split()) or "Local"
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name}-{used[name]}"
        members.append(_member(name, "ollama", model.name))
    return members


def _single_cloud_preset(provider: str) -> Preset:
    return Preset(
        name=f"cloud-{provider}",
        summary=f"{provider} only",
        config=_base_config([_cloud_member(provider, i) for i in range(1, 4)]),
        notice=(
            f"All three members use {provider} - add another key for cross-provider debate."
        ),
    )


def _mixed_preset(provider: str, models: tuple[OllamaModel, ...]) -> Preset:
    return Preset(
        name="mixed",
        summary="1 cloud + 2 local",
        config=_base_config([_cloud_member(provider), *_ollama_members(models)]),
    )


def _local_preset(models: tuple[OllamaModel, ...]) -> Preset:
    return Preset(
        name="local-safe",
        summary="3 local models",
        config=_base_config(_ollama_members(models)),
    )


def _cloud_full_preset() -> Preset:
    return Preset(
        name="cloud-full",
        summary="Anthropic + OpenAI + Google",
        config=_base_config(
            [
                _cloud_member("anthropic"),
                _cloud_member("openai", 2),
                _cloud_member("google"),
            ]
        ),
    )


def _cloud_anthropic_google_preset() -> Preset:
    return Preset(
        name="cloud-anthropic-google",
        summary="Anthropic + Google",
        config=_base_config(
            [
                _cloud_member("anthropic"),
                _cloud_member("anthropic", 2),
                _cloud_member("google"),
            ]
        ),
    )


def _cloud_anthropic_openai_preset() -> Preset:
    return Preset(
        name="cloud-anthropic-openai",
        summary="Anthropic + OpenAI",
        config=_base_config(
            [
                _cloud_member("anthropic"),
                _cloud_member("anthropic", 2),
                _cloud_member("openai", 2),
            ]
        ),
    )


def _cloud_openai_google_preset() -> Preset:
    return Preset(
        name="cloud-openai-google",
        summary="OpenAI + Google",
        config=_base_config(
            [
                _cloud_member("openai"),
                _cloud_member("openai", 2),
                _cloud_member("google"),
            ]
        ),
    )


def select_preset(env: Any) -> Preset:
    """Select the best first-run preset for a detected environment."""
    cloud = _cloud_providers(env)
    usable_local_2 = (
        _smallest_fit(env.ollama_models, 2, env.total_ram_bytes)
        if env.ollama_reachable
        else ()
    )
    usable_local_3 = (
        _smallest_fit(env.ollama_models, 3, env.total_ram_bytes)
        if env.ollama_reachable
        else ()
    )

    if cloud == ["anthropic", "openai", "google"]:
        return _cloud_full_preset()
    if cloud == ["anthropic", "google"]:
        return _cloud_anthropic_google_preset()
    if cloud == ["anthropic", "openai"]:
        return _cloud_anthropic_openai_preset()
    if cloud == ["openai", "google"]:
        return _cloud_openai_google_preset()
    if len(cloud) == 1 and usable_local_2:
        return _mixed_preset(cloud[0], usable_local_2)
    if len(cloud) == 1:
        return _single_cloud_preset(cloud[0])
    if not cloud and usable_local_3:
        return _local_preset(usable_local_3)
    if env.ollama_reachable:
        return build_mock_preset(
            name="mock-ollama-hint",
            notice="Install at least 3 local models, e.g. ollama pull llama3.2:3b",
        )
    return build_mock_preset()
