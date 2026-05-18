"""Shared pytest fixtures for parliament tests."""

from __future__ import annotations

import pytest

from parliament.core.types import Bill, Hansard, Member, Response, Synthesis


@pytest.fixture
def make_hansard():
    """Build a deterministic Hansard with controllable section content.

    Pass empty strings for any synthesis section to test omission paths.
    Members default to a 3-member mock parliament; pass an explicit list
    to override.
    """
    def _factory(
        *,
        question: str = "Should we use Postgres or MongoDB?",
        consensus: str = "All members agree relational structure fits.",
        split: str = "Disagreement on whether to plan sharding now.",
        risks: str = "- Schema migration overhead\n- Read scaling under load",
        recommendation: str = "Postgres. ACID + JSON columns + ecosystem maturity.",
        members: list[Member] | None = None,
        first_reading_content: str = "First-reading content body.",
        debate_content: str = "Debate critique content body.",
        speaker_name: str | None = None,
        duration_ms: int = 12_345,
        hansard_id: str = "12345678-aaaa-bbbb-cccc-deadbeef0000",
        created_at: str = "2026-05-09T12:00:00+00:00",
    ) -> Hansard:
        if members is None:
            members = [
                Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
                Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
            ]
        speaker = speaker_name or members[0].name

        first_reading = [
            Response(
                member_name=m.name,
                content=f"{first_reading_content} ({m.name})",
                phase="first_reading",
                duration_ms=1000,
            )
            for m in members
        ]
        debate = [
            Response(
                member_name=m.name,
                content=f"{debate_content} ({m.name})",
                phase="debate",
                duration_ms=1500,
            )
            for m in members
        ]
        synthesis = Synthesis(
            speaker_name=speaker,
            consensus=consensus,
            split=split,
            risks=risks,
            recommendation=recommendation,
            raw=f"CONSENSUS:\n{consensus}\n\nSPLIT:\n{split}\n\nRISKS:\n{risks}\n\nRECOMMENDATION:\n{recommendation}",
        )

        return Hansard(
            bill=Bill(content=question),
            members=members,
            first_reading=first_reading,
            debate=debate,
            synthesis=synthesis,
            id=hansard_id,
            created_at=created_at,
            duration_ms=duration_ms,
        )

    return _factory
