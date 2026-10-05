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
    assert get_tier("some-future-model", "ollama") == 3


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


@pytest.mark.parametrize(("model", "tier"), [
    ("anthropic/claude-opus-4.6", 1),
    ("anthropic/claude-sonnet-4.6", 2),
    ("anthropic/claude-sonnet-4-6", 2),
    ("openai/gpt-4o", 1),
    ("openai/gpt-4o-mini", 2),
    ("google/gemini-2.5-pro", 1),
    ("google/gemini-2.5-flash", 2),
    ("google/gemini-2.5-flash-lite", 3),
    ("google/gemini-2.0-flash-001", 2),
    ("meta-llama/llama-3.3-70b-instruct", 2),
    ("meta-llama/llama-3.1-70b-instruct", 2),
    ("meta-llama/llama-3.1-8b-instruct", 3),
    ("mistralai/mistral-7b-instruct", 3),
    ("google/gemma-2-9b-it", 3),
    ("qwen/qwen-2.5-72b-instruct", 2),
])
@pytest.mark.parametrize("variant", ["", ":free", ":nitro"])
def test_openrouter_ids_resolve_with_suffixes_and_variants(model, tier, variant):
    api_id = model + variant
    assert get_tier(api_id, "openrouter") == tier
    assert has_known_tier(api_id, "openrouter")
    member = resolve_member_tier(Member(name="A", provider_name="openrouter", model=api_id))
    assert member.tier == tier
    assert member.model == api_id  # the API id is never rewritten


@pytest.mark.parametrize("provider", ["ollama", "openai", "anthropic"])
@pytest.mark.parametrize("model", ["anthropic/claude-opus-4.6", "llama3.1:70b", "user/model:tag"])
def test_other_providers_keep_the_model_id_as_written(provider, model):
    assert canonical_model_id(model, provider) == model


def test_ollama_sizes_stay_distinct():
    assert get_tier("llama3.1:8b", "ollama") == 3
    assert get_tier("llama3.1:70b", "ollama") == 2


def test_aliases_point_at_tier_entries():
    for provider, aliases in MODEL_ALIASES.items():
        for target in aliases.values():
            assert target in MODEL_TIERS, (provider, target)
    assert all("/" not in model for model in MODEL_TIERS)


def _openrouter(*ids):
    return [
        resolve_member_tier(Member(name=f"M{i}", provider_name="openrouter", model=m))
        for i, m in enumerate(ids)
    ]


def test_unlisted_openrouter_model_never_forms_a_gap():
    unknown = "vendor/unlisted:free"
    assert get_tier(unknown, "openrouter") == 3
    assert not has_known_tier(unknown, "openrouter")
    assert not detect_gap(_openrouter("anthropic/claude-opus-4.6", unknown))
    assert detect_gap(_openrouter("anthropic/claude-opus-4.6", unknown, "google/gemma-2-9b-it"))


def test_other_providers_still_count_their_default_tier():
    members = [
        Member(name="A", provider_name="anthropic", model="claude-opus-4-6", tier=1),
        Member(name="B", provider_name="ollama", model="qwen2.5:0.5b", tier=3),
    ]
    assert detect_gap(members) is True
