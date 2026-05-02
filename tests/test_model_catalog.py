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
    payload = {"models": [{"name": "llama3:latest"}, {"name": "gemma2"}, {"name": "mistral"}]}

    def fake_urlopen(url, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    data = model_catalog.fetch_ollama_models("http://localhost:11434/v1")
    assert data.models == ["gemma2", "llama3:latest", "mistral"]
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
