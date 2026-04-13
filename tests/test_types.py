"""Test core types — serialization round-trips, construction."""

import json
from parliament.core.types import Bill, Hansard, Member, Response, Synthesis


def test_bill_auto_title():
    b = Bill(content="Should we use PostgreSQL or MongoDB for analytics?")
    assert b.title == "Should we use PostgreSQL or MongoDB for analytics?"


def test_bill_long_title_truncated():
    long_q = "x" * 100
    b = Bill(content=long_q)
    assert len(b.title) == 60


def test_bill_explicit_title():
    b = Bill(content="long question", title="short")
    assert b.title == "short"


def test_member_str():
    m = Member(name="Claude", provider_name="anthropic", model="claude-sonnet-4-6", tier=2)
    assert "Claude" in str(m)
    assert "anthropic" in str(m)


def test_hansard_to_dict_roundtrip():
    hansard = Hansard(
        bill=Bill(content="test question"),
        members=[
            Member(name="A", provider_name="mock", model="mock-v1", tier=3),
            Member(name="B", provider_name="mock", model="mock-v1", tier=3),
        ],
        first_reading=[
            Response(member_name="A", content="analysis a", phase="first_reading"),
            Response(member_name="B", content="analysis b", phase="first_reading"),
        ],
        debate=[
            Response(member_name="A", content="critique a", phase="debate"),
            Response(member_name="B", content="critique b", phase="debate"),
        ],
        synthesis=Synthesis(
            speaker_name="A",
            consensus="agreed",
            split="disagreed on X",
            risks="risk Y",
            recommendation="do Z",
            raw="full output",
        ),
        duration_ms=1234,
    )

    d = hansard.to_dict()
    assert d["bill"]["content"] == "test question"
    assert len(d["members"]) == 2
    assert d["duration_ms"] == 1234

    # Round-trip
    restored = Hansard.from_dict(d)
    assert restored.bill.content == hansard.bill.content
    assert restored.synthesis.recommendation == "do Z"
    assert len(restored.first_reading) == 2
    assert len(restored.debate) == 2


def test_hansard_json_roundtrip():
    hansard = Hansard(
        bill=Bill(content="json test"),
        members=[Member(name="X", provider_name="mock", model="m", tier=3)],
        first_reading=[],
        debate=[],
        synthesis=Synthesis(speaker_name="X", recommendation="yes"),
    )

    j = hansard.to_json()
    data = json.loads(j)
    restored = Hansard.from_dict(data)
    assert restored.bill.content == "json test"
