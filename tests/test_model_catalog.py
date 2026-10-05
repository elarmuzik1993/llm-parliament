"""Tests for live model discovery."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from parliament import model_catalog


def _fake_response(payload: Any) -> io.BytesIO:
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    body.__enter__ = lambda self=body: self  # type: ignore[attr-defined]
    body.__exit__ = lambda self=body, *a: None  # type: ignore[attr-defined]
    return body


def test_tags_url_strips_v1_suffix() -> None:
    assert model_catalog._ollama_tags_url("http://localhost:11434/v1") == "http://localhost:11434/api/tags"


def test_tags_url_handles_no_v1() -> None:
    assert model_catalog._ollama_tags_url("http://localhost:11434") == "http://localhost:11434/api/tags"


def test_tags_url_handles_trailing_slash() -> None:
    assert model_catalog._ollama_tags_url("http://localhost:11434/v1/") == "http://localhost:11434/api/tags"


def test_ollama_returns_sorted_models(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "models": [
            {"name": "llama3:latest", "size": 3},
            {"name": "gemma2", "size": 1},
            {"name": "mistral", "size": 2},
        ]
    }

    def fake_urlopen(url, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_ollama_models("http://localhost:11434/v1")
    assert data.models == ["gemma2", "llama3:latest", "mistral"]
    assert [(m.name, m.size_bytes) for m in data.ollama_models] == [
        ("gemma2", 1),
        ("llama3:latest", 3),
        ("mistral", 2),
    ]
    assert data.notice is None


def test_ollama_unreachable_returns_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", boom)
    data = model_catalog.fetch_ollama_models("http://localhost:11434/v1")
    assert data.models == []
    assert data.notice is not None
    assert "ollama serve" in data.notice


def test_ollama_empty_list_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url, timeout):
        return _fake_response({"models": []})

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_ollama_models("http://localhost:11434/v1")
    assert data.models == []
    assert "ollama pull" in (data.notice or "")


def test_openai_no_key_returns_notice() -> None:
    data = model_catalog.fetch_openai_models(api_key=None)
    assert data.models == []
    assert "OPENAI_API_KEY" in (data.notice or "")
    assert "parliament keys set openai" in (data.notice or "")


def test_openai_returns_sorted_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}, {"id": "o1-mini"}]}

    def fake_urlopen(req, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_openai_models(api_key="sk-test")
    assert data.models == ["gpt-4o", "gpt-4o-mini", "o1-mini"]
    assert data.notice is None


def test_openai_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(req, timeout):
        raise urllib.error.HTTPError("https://api.openai.com/v1/models", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", boom)
    data = model_catalog.fetch_openai_models(api_key="sk-bad")
    assert data.models == []
    assert "401" in (data.notice or "")


def test_anthropic_no_key_returns_notice() -> None:
    data = model_catalog.fetch_anthropic_models(api_key=None)
    assert data.models == []
    assert "ANTHROPIC_API_KEY" in (data.notice or "")


def test_anthropic_returns_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"data": [{"id": "claude-sonnet-4-6"}, {"id": "claude-opus-4-6"}]}

    def fake_urlopen(req, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_anthropic_models(api_key="sk-ant-test")
    assert data.models == ["claude-opus-4-6", "claude-sonnet-4-6"]


def test_google_no_key_returns_notice() -> None:
    data = model_catalog.fetch_google_models(api_key=None)
    assert data.models == []
    assert "GOOGLE_API_KEY" in (data.notice or "")


def test_google_filters_to_generate_content(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "models": [
            {
                "name": "models/gemini-2.0-flash",
                "supportedGenerationMethods": ["generateContent", "countTokens"],
            },
            {
                "name": "models/embedding-001",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                "name": "models/gemini-2.0-pro",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }

    def fake_urlopen(req, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_google_models(api_key="test-key")
    assert data.models == ["gemini-2.0-flash", "gemini-2.0-pro"]


def test_picker_data_for_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        model_catalog,
        "fetch_ollama_models",
        lambda base_url, timeout=2.0: model_catalog.PickerData(models=["llama3"], notice=None),
    )
    data = model_catalog.picker_data_for("ollama", config={"providers": {"ollama": {"base_url": "x"}}})
    assert data.models == ["llama3"]


def test_picker_data_for_mock_returns_static() -> None:
    data = model_catalog.picker_data_for("mock")
    assert data.models == ["mock-v1", "mock-v2", "mock-v3"]
    assert data.notice is None


def test_picker_data_for_unknown_provider() -> None:
    data = model_catalog.picker_data_for("zzz")
    assert data.models == []
    assert "Unknown provider" in (data.notice or "")


def test_openai_compatible_registry_shape() -> None:
    # Groq, Mistral and OpenRouter speak the OpenAI API at a different address;
    # the registry is what stops that becoming a second client.
    assert set(model_catalog.OPENAI_COMPATIBLE) == {
        "openai",
        "groq",
        "mistral",
        "openrouter",
    }
    assert model_catalog.OPENAI_COMPATIBLE["groq"].base_url == "https://api.groq.com/openai/v1"
    assert model_catalog.OPENAI_COMPATIBLE["mistral"].base_url == "https://api.mistral.ai/v1"
    assert (
        model_catalog.OPENAI_COMPATIBLE["openrouter"].base_url
        == "https://openrouter.ai/api/v1"
    )
    assert model_catalog.OPENAI_COMPATIBLE["groq"].env_var == "GROQ_API_KEY"
    assert model_catalog.OPENAI_COMPATIBLE["mistral"].env_var == "MISTRAL_API_KEY"
    assert model_catalog.OPENAI_COMPATIBLE["openrouter"].env_var == "OPENROUTER_API_KEY"


@pytest.mark.parametrize(
    ("provider", "expected_url"),
    [
        ("openai", "https://api.openai.com/v1/models"),
        ("groq", "https://api.groq.com/openai/v1/models"),
        ("mistral", "https://api.mistral.ai/v1/models"),
        ("openrouter", "https://openrouter.ai/api/v1/models"),
    ],
)
def test_each_provider_is_asked_at_its_own_address(
    provider: str, expected_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        return _fake_response({"data": [{"id": "b"}, {"id": "a"}]})

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_openai_compatible_models(provider, "sk-test")

    assert seen["url"] == expected_url
    assert seen["auth"] == "Bearer sk-test"
    assert data.models == ["a", "b"]
    assert data.notice is None


def test_missing_key_names_that_provider_s_own_env_var() -> None:
    # Telling a Groq user to set OPENAI_API_KEY would be worse than saying
    # nothing, so the notice has to come from the registry.
    notice = model_catalog.fetch_openai_compatible_models("groq", None).notice
    assert notice is not None
    assert "GROQ_API_KEY" in notice
    assert "groq" in notice
    assert "OPENAI_API_KEY" not in notice


def test_unknown_provider_is_reported_not_guessed() -> None:
    data = model_catalog.fetch_openai_compatible_models("nope", "sk-test")
    assert data.models == []
    assert data.notice == "Unknown provider: nope"


def test_picker_routes_the_new_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    seen: dict[str, Any] = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        return _fake_response({"data": [{"id": "llama-3.1-8b-instant"}]})

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.picker_data_for("groq")

    assert seen["url"] == "https://api.groq.com/openai/v1/models"
    assert data.models == ["llama-3.1-8b-instant"]


def test_openai_behaviour_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout):
        assert req.full_url == "https://api.openai.com/v1/models"
        return _fake_response({"data": [{"id": "gpt-4o"}]})

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    assert model_catalog.fetch_openai_models("sk-test").models == ["gpt-4o"]
    assert "OPENAI_API_KEY" in (model_catalog.fetch_openai_models(None).notice or "")


def test_openai_provider_accepts_a_base_url() -> None:
    # The point of the presets: Groq and Mistral are the OpenAI API at another
    # address, and OpenAIProvider used to reject base_url outright with
    # TypeError, so no amount of config could reach them.
    from parliament.providers import create_provider

    groq = create_provider(
        "openai", "llama-3.3-70b-versatile", base_url="https://api.groq.com/openai/v1"
    )
    assert groq._base_url == "https://api.groq.com/openai/v1"

    # Unset stays unset, so the default path still goes to api.openai.com.
    assert create_provider("openai", "gpt-4o")._base_url is None


def test_the_new_models_carry_tiers() -> None:
    from parliament.core.model_tiers import DEFAULT_TIER, get_tier

    assert get_tier("llama-3.3-70b-versatile", "groq") == 2
    assert get_tier("mistral-large-latest", "mistral") == 2
    assert get_tier("mistral-small-latest", "mistral") == 3
    assert get_tier("llama-3.1-8b-instant", "groq") == 3
    # Still the fallback for anything not listed.
    assert get_tier("some-model-nobody-listed", "groq") == DEFAULT_TIER


@pytest.mark.parametrize("vendor", ["openrouter", "groq", "mistral"])
def test_discovery_uses_only_the_vendor_key(vendor: str, monkeypatch: pytest.MonkeyPatch) -> None:
    env_var = model_catalog.OPENAI_COMPATIBLE[vendor].env_var
    monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    assert model_catalog.openai_compatible_key(vendor) is None
    monkeypatch.setenv(env_var, "vendor-test-key")
    assert model_catalog.openai_compatible_key(vendor) == "vendor-test-key"
    assert model_catalog.openai_compatible_key("nope") is None
