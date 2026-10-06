"""Integration test — full pipeline with mock providers, no API calls."""

import pytest

from parliament.config import KEY_PROVIDERS
from parliament.core.parliament import Parliament, select_speaker
from parliament.core.types import Member
from parliament.providers.mock import MockProvider


async def test_openrouter_frontier_is_speaker_and_api_ids_are_unchanged():
    ids = ["anthropic/claude-sonnet-4.6", "openai/gpt-4o-mini", "anthropic/claude-opus-4.6"]
    members = [Member(name=str(i), provider_name="openrouter", model=m) for i, m in enumerate(ids)]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    hansard = await Parliament(members, providers).ask("Which database?")
    assert hansard.synthesis.speaker_name == "2"
    assert [m.tier for m in hansard.members] == [2, 2, 1]
    assert [m.model for m in hansard.members] == ids


def test_gap_warning_names_only_classified_openrouter_members():
    members = [
        Member(name="Unknown", provider_name="openrouter", model="vendor/unlisted"),
        Member(name="Opus", provider_name="openrouter", model="anthropic/claude-opus-4.6"),
        Member(name="Gemma", provider_name="openrouter", model="google/gemma-2-9b-it"),
    ]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    assert Parliament(members[:2], providers).check_gaps() == []
    (warning,) = Parliament(members, providers).check_gaps()
    assert "Opus (tier 1)" in warning and "Gemma (tier 3)" in warning
    assert "Unknown" not in warning


@pytest.fixture
def mock_parliament_3():
    """3-member parliament with mock providers."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
        Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
    ]
    providers = {
        "Alpha": MockProvider(model="mock-v1"),
        "Beta": MockProvider(model="mock-v2"),
        "Gamma": MockProvider(model="mock-v3"),
    }
    return Parliament(members=members, providers=providers)


@pytest.fixture
def mock_parliament_2():
    """2-member parliament with mock providers."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
    ]
    providers = {
        "Alpha": MockProvider(model="mock-v1"),
        "Beta": MockProvider(model="mock-v2"),
    }
    return Parliament(members=members, providers=providers)


async def test_full_pipeline_3_members(mock_parliament_3):
    """3 mock members → full pipeline → valid Hansard."""
    hansard = await mock_parliament_3.ask("PostgreSQL or MongoDB?")

    assert hansard.bill.content == "PostgreSQL or MongoDB?"
    assert len(hansard.members) == 3
    assert len(hansard.first_reading) == 3
    assert len(hansard.debate) == 3
    assert hansard.synthesis.speaker_name in ["Alpha", "Beta", "Gamma"]
    assert hansard.duration_ms > 0
    assert hansard.id  # UUID present


async def test_full_pipeline_2_members(mock_parliament_2):
    """2 mock members → full pipeline → valid Hansard."""
    hansard = await mock_parliament_2.ask("REST or GraphQL?")

    assert len(hansard.members) == 2
    assert len(hansard.first_reading) == 2
    assert len(hansard.debate) == 2


async def test_hansard_serializable(mock_parliament_3):
    """Hansard should round-trip through JSON."""
    import json

    from parliament.core.types import Hansard

    hansard = await mock_parliament_3.ask("Test question")
    j = hansard.to_json()
    data = json.loads(j)
    restored = Hansard.from_dict(data)
    assert restored.bill.content == "Test question"


def test_minimum_members():
    """Parliament with < 2 members should raise."""
    with pytest.raises(ValueError, match="at least 2"):
        Parliament(
            members=[Member(name="Solo", provider_name="mock", model="m", tier=3)],
            providers={"Solo": MockProvider()},
        )


def test_maximum_members():
    """Parliament with > 3 members should raise."""
    members = [
        Member(name=f"M{i}", provider_name="mock", model="m", tier=3)
        for i in range(4)
    ]
    providers = {f"M{i}": MockProvider() for i in range(4)}
    with pytest.raises(ValueError, match="at most 3"):
        Parliament(members=members, providers=providers)


def test_missing_provider():
    """Member without a matching provider should raise."""
    members = [
        Member(name="A", provider_name="mock", model="m", tier=3),
        Member(name="B", provider_name="mock", model="m", tier=3),
    ]
    with pytest.raises(ValueError, match="No provider"):
        Parliament(members=members, providers={"A": MockProvider()})


def test_speaker_override():
    members = [
        Member(name="A", provider_name="mock", model="m", tier=3),
        Member(name="B", provider_name="mock", model="m", tier=2),
    ]
    providers = {"A": MockProvider(), "B": MockProvider()}

    # Without override, B is stronger (tier 2)
    speaker, _ = select_speaker(members, providers)
    assert speaker.name == "B"

    # With override, A is forced
    speaker, _ = select_speaker(members, providers, override="A")
    assert speaker.name == "A"


def test_speaker_tier_awareness():
    """Strongest tier should be Speaker by default."""
    members = [
        Member(name="Strong", provider_name="mock", model="m", tier=1),
        Member(name="Weak", provider_name="mock", model="m", tier=3),
    ]
    providers = {"Strong": MockProvider(), "Weak": MockProvider()}
    speaker, _ = select_speaker(members, providers)
    assert speaker.name == "Strong"


def test_speaker_rotation_among_equal():
    """Equal-tier members should rotate."""
    members = [
        Member(name="A", provider_name="mock", model="m", tier=2),
        Member(name="B", provider_name="mock", model="m", tier=2),
    ]
    providers = {"A": MockProvider(), "B": MockProvider()}

    speaker1, _ = select_speaker(members, providers, last_speaker=None)
    assert speaker1.name == "A"

    speaker2, _ = select_speaker(members, providers, last_speaker="A")
    assert speaker2.name == "B"

    speaker3, _ = select_speaker(members, providers, last_speaker="B")
    assert speaker3.name == "A"


@pytest.mark.parametrize("provider", ["ollama", *KEY_PROVIDERS])
def test_gap_warnings_exclude_fallback_ratings_for_every_provider(provider):
    members = [
        Member(name="Unknown", provider_name=provider, model="unassessed-model"),
        Member(name="GPT", provider_name="openai", model="gpt-4o"),
        Member(name="Llama", provider_name="ollama", model="llama3.1"),
    ]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    parliament = Parliament(members[:2], providers)
    assert [m.tier for m in parliament.members] == [3, 1]
    assert parliament.check_gaps() == []

    warnings = Parliament(members, providers).check_gaps()
    assert len(warnings) == 1
    assert "GPT (tier 1)" in warnings[0]
    assert "Llama (tier 3)" in warnings[0]
    assert "Unknown" not in warnings[0]


def test_unknown_model_remains_eligible_for_speaker_with_fallback_tier():
    members = [
        Member(name="Unknown", provider_name="ollama", model="unassessed-model"),
        Member(name="Tiny", provider_name="ollama", model="tinyllama"),
    ]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    parliament = Parliament(members, providers)
    assert [m.tier for m in parliament.members] == [3, 4]
    assert parliament.check_gaps() == []
    assert select_speaker(parliament.members, providers)[0].name == "Unknown"


def test_gap_warning_uses_comparison_tiers_even_if_member_tiers_are_stale():
    members = [Member("GPT", "openai", "gpt-4o"), Member("Tiny", "ollama", "tinyllama")]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    parliament = Parliament(members, providers)
    for member in members:
        member.tier = 3
    assert parliament.check_gaps() == [
        "Large capability gap between GPT (tier 1) and Tiny (tier 4). "
        "Debate quality is limited by the weakest member."
    ]


def test_runtime_gap_warning_preserves_explicit_mock_tiers():
    members = [Member("Strong", "mock", "m", tier=1), Member("Weak", "mock", "m", tier=4)]
    providers = {m.name: MockProvider(model=m.model) for m in members}
    parliament = Parliament(members, providers)
    assert [m.tier for m in parliament.members] == [1, 4]
    assert "Strong (tier 1) and Weak (tier 4)" in parliament.check_gaps()[0]


def test_runtime_reads_endpoint_from_programmatically_created_providers():
    from parliament.providers.openai_provider import OpenAIProvider

    members = [
        Member(name="Gemma", provider_name="openai", model="google/gemma-2-9b-it"),
        Member(name="Opus", provider_name="openai", model="anthropic/claude-opus-4.6"),
    ]
    providers = {
        m.name: OpenAIProvider(model=m.model, base_url="https://openrouter.ai/api/v1")
        for m in members
    }
    parliament = Parliament(members, providers)
    assert [m.tier for m in parliament.members] == [3, 1]
    assert select_speaker(parliament.members, providers)[0].name == "Opus"
    assert len(parliament.check_gaps()) == 1
