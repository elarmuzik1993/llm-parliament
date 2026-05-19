"""Tests for configured-member doctor checks."""

from __future__ import annotations

from parliament import doctor
from parliament.model_catalog import OllamaModel, PickerData


def _cfg(members):
    return {
        "parliament": {"name": "Test", "members": members},
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }


def test_cloud_member_missing_key_warns(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    results = doctor._check_member_viability(
        _cfg([{"name": "Claude", "provider": "anthropic", "model": "claude-sonnet-4-6"}])
    )

    assert len(results) == 1
    assert results[0].warn is True
    assert "ANTHROPIC_API_KEY" in results[0].message


def test_ollama_member_not_pulled_warns(monkeypatch) -> None:
    monkeypatch.setattr(
        "parliament.model_catalog.fetch_ollama_models",
        lambda base_url: PickerData(models=["gemma2"], ollama_models=(OllamaModel("gemma2", 1),)),
    )

    results = doctor._check_member_viability(
        _cfg([{"name": "Llama", "provider": "ollama", "model": "llama3.2:3b"}])
    )

    assert any(r.warn and "ollama pull llama3.2:3b" in r.message for r in results)


def test_ollama_aggregate_oom_warns(monkeypatch) -> None:
    monkeypatch.setattr(
        "parliament.model_catalog.fetch_ollama_models",
        lambda base_url: PickerData(
            models=["a", "b"],
            ollama_models=(
                OllamaModel("a", 8 * 1024**3),
                OllamaModel("b", 8 * 1024**3),
            ),
        ),
    )
    monkeypatch.setattr(doctor, "_system_ram_bytes", lambda: 16 * 1024**3)

    results = doctor._check_member_viability(
        _cfg(
            [
                {"name": "A", "provider": "ollama", "model": "a"},
                {"name": "B", "provider": "ollama", "model": "b"},
            ]
        )
    )

    assert any(r.warn and "may OOM" in r.message for r in results)


def test_mock_only_members_emit_no_member_results() -> None:
    results = doctor._check_member_viability(
        _cfg([{"name": "Mock-A", "provider": "mock", "model": "mock-v1"}])
    )

    assert results == []


def test_psutil_missing_skips_only_ram_check(monkeypatch) -> None:
    monkeypatch.setattr(
        "parliament.model_catalog.fetch_ollama_models",
        lambda base_url: PickerData(
            models=["a"],
            ollama_models=(OllamaModel("a", 1 * 1024**3),),
        ),
    )
    monkeypatch.setattr(doctor, "_system_ram_bytes", lambda: None)

    results = doctor._check_member_viability(
        _cfg([{"name": "A", "provider": "ollama", "model": "a"}])
    )

    assert any("installed" in r.message for r in results)
    assert any(r.info and "RAM check skipped" in r.message for r in results)
