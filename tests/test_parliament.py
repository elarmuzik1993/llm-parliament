"""Integration test — full pipeline with mock providers, no API calls."""

import pytest
from parliament.core.types import Member
from parliament.core.parliament import Parliament, select_speaker
from parliament.providers.mock import MockProvider


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
    from parliament.core.types import Hansard
    import json

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
