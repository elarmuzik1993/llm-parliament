"""Test model tier system."""

import re
from pathlib import Path

import pytest

from parliament.config import KEY_PROVIDERS
from parliament.core.model_tiers import (
    FAMILY_RULES,
    MODEL_ALIASES,
    MODEL_TIERS,
    calculate_gap,
    canonical_model_id,
    detect_gap,
    get_member_tier_label,
    get_tier,
    get_tier_label,
    has_known_tier,
    inferred_tier,
    is_inferred_tier,
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
    gap = calculate_gap(members).gap
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
def test_calculate_gap_reports_no_assessed_large_gap(members):
    assert calculate_gap(members).gap is None
    assert not detect_gap(members)


def test_gap_and_resolution_preserve_supplied_mock_tiers():
    strongest = Member("Mock strongest", "mock", "unlisted", tier=1)
    weakest = Member("Mock weakest", "mock", "gpt-4o", tier=4)
    gap = calculate_gap([weakest, strongest]).gap
    assert gap is not None
    assert gap.strongest is strongest and gap.strongest_tier == 1
    assert gap.weakest is weakest and gap.weakest_tier == 4
    assert resolve_member_tier(strongest).tier == 1
    assert resolve_member_tier(weakest).tier == 4


def test_comparable_is_distinct_from_missing_ratings():
    rated = [Member("GPT", "openai", "gpt-4o"), Member("Pro", "google", "gemini-2.5-pro")]
    comparable = calculate_gap(rated)
    assert comparable.comparable
    assert comparable.warnings() == []
    unknown = Member("Mystery", "ollama", "unassessed")
    incomplete = calculate_gap(rated + [unknown])
    assert incomplete.gap is None
    assert not incomplete.comparable
    assert incomplete.unrated_members == (unknown,)
    assert "Mystery (unrated, assumed tier 3)" in incomplete.warnings()[0]


def test_assessed_gap_and_unrated_members_both_remain_visible():
    members = [
        Member("GPT", "openai", "gpt-4o"), Member("Tiny", "ollama", "tinyllama"),
        Member("Mystery", "ollama", "unassessed"),
    ]
    result = calculate_gap(members)
    assert result.gap is not None
    assert not result.comparable
    assert [m.name for m in result.unrated_members] == ["Mystery"]
    assert len(result.warnings()) == 2
    assert [w.kind for w in result.session_warnings()] == ["tier_gap", "unrated"]


def test_all_unrated_and_insufficient_members_are_not_comparable():
    unknowns = [Member("A", "ollama", "unassessed"), Member("B", "openai", "unassessed")]
    result = calculate_gap(unknowns)
    assert result.rated_count == 0
    assert result.unrated_members == tuple(unknowns)
    assert len(result.warnings()) == 1
    assert not result.comparable
    for members in ([], [Member("GPT", "openai", "gpt-4o")]):
        assert not calculate_gap(members).comparable


# Family rules (#67). Every rule needs at least one id here, so a pattern
# cannot be added, or widened, without saying what it is meant to rate.
@pytest.mark.parametrize(("model", "provider", "tier"), [
    ("claude-opus-4-1", "anthropic", 1),
    ("claude-opus-5-5", "anthropic", 1),
    ("anthropic/claude-opus-5.5", "openrouter", 1),
    ("claude-sonnet-4-5", "anthropic", 2),
    ("anthropic/claude-sonnet-5.5:nitro", "openrouter", 2),
    ("claude-haiku-5-5", "anthropic", 3),
    ("anthropic/claude-haiku-4.5", "openrouter", 3),
    ("gpt-5", "openai", 1),
    ("openai/gpt-5.1", "openrouter", 1),
    ("gpt-5-mini", "openai", 2),
    ("openai/gpt-5.1-mini:free", "openrouter", 2),
    ("gpt-5-nano", "openai", 3),
    ("gemini-3-pro-preview", "google", 1),
    ("google/gemini-3.5-pro", "openrouter", 1),
    ("gemini-3-flash", "google", 2),
    ("gemini-3-flash-lite-preview", "google", 3),
])
def test_family_rules_rate_newer_releases_as_inferred(model, provider, tier):
    assert get_tier(model, provider) == tier
    assert has_known_tier(model, provider)
    assert is_inferred_tier(model, provider)
    member = resolve_member_tier(Member("M", provider, model))
    assert get_member_tier_label(member).endswith("(inferred)")
    assert member.model == model  # the API id is never rewritten


def test_every_family_rule_has_an_example():
    examples = [
        "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5",
        "gpt-5", "gpt-5-mini", "gpt-5-nano",
        "gemini-3-pro", "gemini-3-flash", "gemini-3-flash-lite",
    ]
    matched = {
        pattern for pattern, _ in FAMILY_RULES
        if any(re.fullmatch(pattern, example) for example in examples)
    }
    assert matched == {pattern for pattern, _ in FAMILY_RULES}


@pytest.mark.parametrize("model", [
    "claude-3-opus",            # superseded generation, old naming
    "claude-opus-3",            # below the current major version
    "claude-opus-5-5-custom",   # a fine-tune keeps nothing of the family rating
    "claude-opus-4-5-20251101",  # dated snapshot: pin it in MODEL_TIERS instead
    "gpt-4.1",                  # below the current major version
    "gpt-5-codex",              # unknown variant
    "gpt-5.6-sol",
    "gpt-5-2025-08-07",
    "gemini-1.5-pro",
    "gemini-2.0-flash-002",     # revision suffix, as the OpenRouter rule
    "gemini-3-pro-exp",
    "my-gpt-5",
])
def test_family_rules_leave_variants_and_old_generations_unrated(model):
    assert inferred_tier(model) is None
    assert not has_known_tier(model, "anthropic")
    assert not has_known_tier(model, "openai")


def test_family_rules_agree_with_the_table_wherever_both_apply():
    """MODEL_TIERS wins, so a disagreement would be invisible without this."""
    for model, tier in MODEL_TIERS.items():
        inferred = inferred_tier(model)
        assert inferred in (None, tier), (model, tier, inferred)


def test_assessed_ratings_are_not_labelled_inferred():
    member = resolve_member_tier(Member("M", "anthropic", "claude-opus-4-6"))
    assert get_member_tier_label(member) == "frontier"
    assert not is_inferred_tier("claude-opus-4-6", "anthropic")


def test_every_model_a_preset_ships_with_is_rated():
    from parliament import presets

    shipped = [
        ("anthropic", presets.CLAUDE_SONNET), ("anthropic", presets.CLAUDE_HAIKU),
        ("openai", presets.GPT_4O), ("openai", presets.GPT_4O_MINI),
        ("google", presets.GEMINI_FLASH), ("google", presets.GEMINI_FLASH_LITE),
    ]
    # The OpenRouter preset lists its ids inline rather than as constants.
    source = Path(presets.__file__).read_text(encoding="utf-8")
    shipped += [("openrouter", m) for m in re.findall(r'"openrouter", "([^"]+)"', source)]
    assert len(shipped) > 6
    for provider, model in shipped:
        assert has_known_tier(model, provider), (provider, model)
