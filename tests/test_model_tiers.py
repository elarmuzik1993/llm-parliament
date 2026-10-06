"""Test model tier system."""

import pytest

from parliament.config import KEY_PROVIDERS
from parliament.core.model_tiers import (
    MODEL_ALIASES,
    MODEL_TIERS,
    calculate_gap,
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


def test_assessed_revision_takes_precedence_over_aliases(monkeypatch):
    monkeypatch.setitem(MODEL_TIERS, "gemini-2.0-flash-001", 1)
    model = "google/gemini-2.0-flash-001:free"
    assert canonical_model_id(model, "openrouter") == "gemini-2.0-flash-001"
    assert get_tier(model, "openrouter") == 1


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


def test_other_providers_do_not_compare_unknown_default_tiers():
    members = [
        Member(name="A", provider_name="anthropic", model="claude-opus-4-6", tier=1),
        Member(name="B", provider_name="ollama", model="qwen2.5:0.5b", tier=3),
    ]
    assert detect_gap(members) is False


@pytest.mark.parametrize("model", [
    "vendor/gpt-4o-instruct",
    "vendor/gpt-4o-it",
    "google/gemini-2.0-flash-002",
    "meta-llama/llama-3.1-13b-instruct",
    "meta-llama/llama-3.4-70b-instruct",
    "mistralai/mistral-8b-instruct",
    "google/gemma-3-9b-it",
])
def test_unestablished_suffixes_versions_and_sizes_stay_unknown(model):
    assert canonical_model_id(model, "openrouter") == model.split("/", 1)[1]
    assert not has_known_tier(model, "openrouter")
    assert get_tier(model, "openrouter") == 3


@pytest.mark.parametrize("provider", ["ollama", "openai", "custom"])
@pytest.mark.parametrize("model", [
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "google/gemma-2-9b-it",
])
def test_openrouter_suffix_aliases_do_not_affect_other_providers(provider, model):
    assert canonical_model_id(model, provider) == model
    assert not has_known_tier(model, provider)


@pytest.mark.parametrize("base_url", [
    "https://openrouter.ai/api/v1",
    "https://openrouter.ai/api/v1/",
    "https://OPENROUTER.AI:443/api/v1/",
])
@pytest.mark.parametrize(("model", "canonical", "tier"), [
    ("anthropic/claude-opus-4.6:nitro", "claude-opus-4-6", 1),
    ("meta-llama/llama-3.1-70b-instruct", "llama3.1:70b", 2),
    ("google/gemma-2-9b-it:free", "gemma2:9b", 3),
])
def test_openai_at_openrouter_uses_the_same_tier_identity(base_url, model, canonical, tier):
    assert canonical_model_id(model, "openai", base_url) == canonical
    assert has_known_tier(model, "openai", base_url)
    assert get_tier(model, "openai", base_url) == tier


@pytest.mark.parametrize("base_url", [
    None,
    "",
    "https://api.openai.com/v1",
    "https://gateway.internal/v1",
    "https://openrouter.ai.evil.example/api/v1",
    "https://evil.example/openrouter.ai/api/v1",
    "https://openrouter.ai/api/v10",
    "https://openrouter.ai/api/v1/models",
    "http://openrouter.ai/api/v1",
    "https://openrouter.ai:8443/api/v1",
    "https://openrouter.ai:0/api/v1",
    "https://openrouter.ai:invalid/api/v1",
    "https://[invalid/api/v1",
    "https://openrouter.ai/api/v1?redirect=other",
    "https://openrouter.ai/api/v1#other",
    "https://user:secret@openrouter.ai/api/v1",
])
def test_other_endpoints_do_not_inherit_openrouter_rules(base_url):
    model = "anthropic/claude-opus-4.6"
    assert canonical_model_id(model, "openai", base_url) == model
    assert not has_known_tier(model, "openai", base_url)
    assert get_tier(model, "openai", base_url) == 3


@pytest.mark.parametrize("provider", ["ollama", "anthropic", "google", "custom"])
def test_endpoint_inference_is_limited_to_openai_compatible_configuration(provider):
    base_url = "https://openrouter.ai/api/v1"
    model = "user/model:tag"
    assert canonical_model_id(model, provider, base_url) == model


@pytest.mark.parametrize("provider", ["ollama", *KEY_PROVIDERS])
def test_unknown_members_do_not_form_a_gap_for_any_provider(provider):
    assert not detect_gap([])
    assert not detect_gap([
        Member(name="A", provider_name=provider, model="unassessed-model", tier=1),
        Member(name="B", provider_name=provider, model="another-unassessed-model", tier=4),
    ])


@pytest.mark.parametrize(("provider", "model", "base_url"), [
    ("openai", "gpt-4o", None),
    ("openrouter", "anthropic/claude-opus-4.6", None),
    ("openai", "anthropic/claude-opus-4.6", "https://openrouter.ai/api/v1"),
])
def test_gap_resolves_known_comparison_tiers_without_mutating_members(provider, model, base_url):
    frontier = Member(name="Frontier", provider_name=provider, model=model, base_url=base_url)
    small = Member(name="Small", provider_name="ollama", model="tinyllama", tier=1)
    unknown = Member(name="Unknown", provider_name="ollama", model="unassessed", tier=4)
    members = [unknown, small, frontier]
    gap = calculate_gap(members)
    assert gap is not None
    assert gap.strongest is frontier and gap.strongest_tier == 1
    assert gap.weakest is small and gap.weakest_tier == 4
    assert detect_gap(members)
    assert [m.tier for m in members] == [4, 1, 3]
    assert frontier.model == model


@pytest.mark.parametrize("members", [
    [],
    [Member("Single", "openai", "gpt-4o")],
    [Member("Unknown", "ollama", "unassessed"), Member("Known", "openai", "gpt-4o")],
    [Member("A", "openai", "gpt-4o"), Member("B", "openai", "gpt-4o-mini")],
    [Member("A", "openai", "gpt-4o"), Member("B", "google", "gemini-2.5-pro")],
])
def test_calculate_gap_returns_none_without_a_comparable_large_gap(members):
    assert calculate_gap(members) is None
    assert not detect_gap(members)


def test_gap_and_resolution_preserve_supplied_mock_tiers():
    strongest = Member("Mock strongest", "mock", "unlisted", tier=1)
    weakest = Member("Mock weakest", "mock", "gpt-4o", tier=4)
    gap = calculate_gap([weakest, strongest])
    assert gap is not None
    assert gap.strongest is strongest and gap.strongest_tier == 1
    assert gap.weakest is weakest and gap.weakest_tier == 4
    assert resolve_member_tier(strongest).tier == 1
    assert resolve_member_tier(weakest).tier == 4
