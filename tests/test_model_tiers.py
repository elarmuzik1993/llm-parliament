"""Test model tier system."""

import pytest

from parliament.core.model_tiers import (
    MODEL_ALIASES,
    MODEL_TIERS,
    canonical_model_id,
    detect_gap,
    get_tier,
    get_tier_label,
    has_known_tier,
    resolve_member_tier,
)
from parliament.core.types import Member


def test_known_models():
    assert get_tier("claude-opus-4-6", "anthropic") == 1
    assert get_tier("claude-sonnet-4-6", "anthropic") == 2
    assert get_tier("llama3.1", "ollama") == 3
    assert get_tier("tinyllama", "ollama") == 4


def test_unknown_model_defaults_to_3():
    assert get_tier("some-future-model", "openrouter") == 3


def test_tier_labels():
    assert get_tier_label(1) == "frontier"
    assert get_tier_label(4) == "small"


def test_no_gap_same_tier():
    members = [
        Member(name="A", provider_name="openai", model="gpt-4o-mini", tier=2),
        Member(name="B", provider_name="anthropic", model="claude-sonnet-4-6", tier=2),
    ]
    assert detect_gap(members) is False


def test_no_gap_adjacent_tiers():
    members = [
        Member(name="A", provider_name="openai", model="gpt-4o", tier=1),
        Member(name="B", provider_name="openai", model="gpt-4o-mini", tier=2),
    ]
    assert detect_gap(members) is False


def test_gap_detected():
    members = [
        Member(name="A", provider_name="openai", model="gpt-4o", tier=1),
        Member(name="B", provider_name="ollama", model="llama3.1", tier=3),
    ]
    assert detect_gap(members) is True


def test_gap_single_member():
    members = [Member(name="A", provider_name="mock", model="m", tier=1)]
    assert detect_gap(members) is False


@pytest.mark.parametrize(("model", "canonical", "tier"), [
    ("anthropic/claude-opus-4.6", "claude-opus-4-6", 1),
    ("anthropic/claude-sonnet-4.6", "claude-sonnet-4-6", 2),
    ("anthropic/claude-sonnet-4-6", "claude-sonnet-4-6", 2),
    ("openai/gpt-4o", "gpt-4o", 1),
    ("google/gemini-2.5-pro", "gemini-2.5-pro", 1),
    ("google/gemini-2.5-flash", "gemini-2.5-flash", 2),
    ("meta-llama/llama-3.3-70b-instruct", "llama-3.3-70b-versatile", 2),
])
@pytest.mark.parametrize("variant", ["", ":free", ":nitro"])
def test_openrouter_identity_and_variants(model, canonical, tier, variant):
    api_id = model + variant
    assert canonical_model_id(api_id, "openrouter") == canonical
    assert get_tier(api_id, "openrouter") == tier
    member = resolve_member_tier(Member(name="A", provider_name="openrouter", model=api_id))
    assert member.tier == tier
    assert member.model == api_id


@pytest.mark.parametrize("provider", ["ollama", "openai", "custom"])
@pytest.mark.parametrize("model", [
    "anthropic/claude-opus-4.6", "llama3.1:8b", "llama3.1:70b", "user/model:tag",
])
def test_other_providers_preserve_model_identity(provider, model):
    assert canonical_model_id(model, provider) == model


def test_ollama_sizes_remain_distinct():
    assert get_tier("llama3.1:8b", "ollama") == 3
    assert get_tier("llama3.1:70b", "ollama") == 2
    assert get_tier("anthropic/claude-opus-4.6", "openai") == 3


def test_alias_targets_are_canonical_tier_entries():
    for provider, aliases in MODEL_ALIASES.items():
        for alias, canonical in aliases.items():
            assert canonical in MODEL_TIERS
            assert canonical_model_id(alias, provider) == canonical
    assert all("/" not in model for model in MODEL_TIERS)


def test_known_tier_three_is_distinct_from_unknown():
    assert has_known_tier("google/gemini-2.5-flash-lite", "openrouter")
    assert not has_known_tier("vendor/unlisted:free", "openrouter")
    assert get_tier("vendor/unlisted:free", "openrouter") == 3


@pytest.mark.parametrize(("other", "expected"), [
    ("vendor/unlisted:free", False),
    ("google/gemini-2.5-flash-lite", True),
])
def test_openrouter_gap_uses_only_known_models(other, expected):
    members = [
        resolve_member_tier(Member(name=name, provider_name="openrouter", model=model))
        for name, model in [("Opus", "anthropic/claude-opus-4.6"), ("Other", other)]
    ]
    assert detect_gap(members) is expected


def test_unknown_members_do_not_form_a_gap():
    assert not detect_gap([])
    assert not detect_gap([
        Member(name="A", provider_name="openrouter", model="vendor/unknown", tier=1),
        Member(name="B", provider_name="openrouter", model="vendor/other", tier=4),
    ])
