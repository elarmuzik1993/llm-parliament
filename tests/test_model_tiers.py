"""Test model tier system."""

from parliament.core.types import Member
from parliament.core.model_tiers import get_tier, get_tier_label, detect_gap


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
