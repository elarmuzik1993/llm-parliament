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


def test_fetch_returns_sorted_names(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"models": [{"name": "llama3:latest"}, {"name": "gemma2"}, {"name": "mistral"}]}

    def fake_urlopen(url, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    result = model_catalog.fetch_ollama_models("http://localhost:11434/v1")
    assert result == ["gemma2", "llama3:latest", "mistral"]


def test_fetch_returns_none_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", boom)
    assert model_catalog.fetch_ollama_models("http://localhost:11434/v1") is None


def test_fetch_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", boom)
    assert model_catalog.fetch_ollama_models("http://localhost:11434/v1") is None


def test_fetch_returns_none_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    def fake_urlopen(url, timeout):
        return BadResponse(b"not json")

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    assert model_catalog.fetch_ollama_models("http://localhost:11434/v1") is None


def test_fetch_skips_malformed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "models": [
            {"name": "llama3:latest"},
            {"name": ""},
            {"size": 123},
            "garbage",
            {"name": "gemma2"},
        ]
    }

    def fake_urlopen(url, timeout):
        return _fake_response(payload)

    monkeypatch.setattr(model_catalog.urllib.request, "urlopen", fake_urlopen)
    assert model_catalog.fetch_ollama_models("http://localhost:11434/v1") == ["gemma2", "llama3:latest"]
