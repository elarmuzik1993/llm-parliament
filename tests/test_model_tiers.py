"""Test model tier system."""

from parliament.core.model_tiers import detect_gap, get_tier, get_tier_label
from parliament.core.types import Member


def test_known_models():
    assert get_tier("claude-opus-4-6") == 1
    assert get_tier("claude-sonnet-4-6") == 2
    assert get_tier("llama3.1") == 3
    assert get_tier("tinyllama") == 4


def test_unknown_model_defaults_to_3():
    assert get_tier("some-future-model") == 3


def test_tier_labels():
    assert get_tier_label(1) == "frontier"
    assert get_tier_label(4) == "small"


def test_no_gap_same_tier():
    members = [
        Member(name="A", provider_name="mock", model="m", tier=2),
        Member(name="B", provider_name="mock", model="m", tier=2),
    ]
    assert detect_gap(members) is False


def test_no_gap_adjacent_tiers():
    members = [
        Member(name="A", provider_name="mock", model="m", tier=1),
        Member(name="B", provider_name="mock", model="m", tier=2),
    ]
    assert detect_gap(members) is False


def test_gap_detected():
    members = [
        Member(name="A", provider_name="mock", model="m", tier=1),
        Member(name="B", provider_name="mock", model="m", tier=3),
    ]
    assert detect_gap(members) is True


def test_gap_single_member():
    members = [Member(name="A", provider_name="mock", model="m", tier=1)]
    assert detect_gap(members) is False


def test_openrouter_slug_resolves_to_bare_id_tier():
    assert get_tier("anthropic/claude-opus-4-6") == 1
    assert get_tier("openai/gpt-4o") == 1
    assert get_tier("google/gemini-2.5-pro") == 1
    assert get_tier("openai/gpt-4o-mini") == 2


def test_openrouter_claude_dot_version_matches_anthropic_dash_id():
    assert get_tier("anthropic/claude-opus-4.6") == 1
    assert get_tier("anthropic/claude-sonnet-4.6") == 2
    # Gemini's dot is part of the real id and must not be rewritten away.
    assert get_tier("google/gemini-2.5-flash-lite") == 3


def test_openrouter_routing_variant_is_ignored():
    assert get_tier("anthropic/claude-sonnet-4.6:free") == 2
    assert get_tier("google/gemini-2.5-pro:thinking") == 1


def test_ollama_tag_is_not_treated_as_a_variant():
    assert get_tier("llama3.1:70b") == 2
    assert get_tier("llama3.1:8b") == 3


def test_unknown_openrouter_slug_defaults_to_3():
    assert get_tier("some-lab/some-future-model:free") == 3


def test_gap_fires_for_an_all_openrouter_parliament():
    members = [
        Member(name=m, provider_name="openrouter", model=m, tier=get_tier(m))
        for m in ("anthropic/claude-opus-4.6", "google/gemini-2.5-flash-lite")
    ]
    assert detect_gap(members) is True
