"""Test core types — serialization round-trips, construction."""

import json
from dataclasses import replace

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


def test_member_endpoint_survives_replace_but_stays_out_of_public_data():
    from parliament.core.model_tiers import resolve_member_tier

    member = Member("Opus", "openai", "anthropic/claude-opus-4.6",
                    base_url="https://openrouter.ai/api/v1")
    copied = replace(member, name="Copy")
    assert copied.base_url == member.base_url
    assert resolve_member_tier(copied).tier == 1
    assert "openrouter.ai" not in repr(copied)
    assert replace(member, base_url="https://other.example/v1") == member
    hansard = Hansard(Bill("Q"), [copied], [], [], Synthesis("Copy"), unrated_members=[])
    data = hansard.to_dict()
    assert set(data["members"][0]) == {"name", "provider_name", "model", "tier"}
    assert "openrouter.ai" not in hansard.to_json()
    assert Hansard.from_dict(data).members == hansard.members


def test_unrated_members_json_roundtrip_and_old_records():
    hansard = Hansard(Bill("Q"), [Member("Mystery", "ollama", "unassessed")], [], [],
                      Synthesis("Mystery"), unrated_members=["Mystery"])
    data = json.loads(hansard.to_json())
    assert data["unrated_members"] == ["Mystery"]
    assert Hansard.from_dict(data).unrated_members == ["Mystery"]
    data.pop("unrated_members")
    assert Hansard.from_dict(data).unrated_members == []
