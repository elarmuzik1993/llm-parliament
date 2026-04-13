"""Orchestrator — the public API entry point."""

from __future__ import annotations

import time
from typing import Callable

from parliament.core.types import Bill, Hansard, Member
from parliament.core.model_tiers import detect_gap, resolve_member_tier
from parliament.providers.base import Provider
from parliament.procedures.first_reading import run_first_reading
from parliament.procedures.debate import run_debate
from parliament.procedures.division import run_division


# (phase, member_name, status)
ProgressCallback = Callable[[str, str, str], None]


def _noop_progress(phase: str, member: str, status: str) -> None:
    pass


def select_speaker(
    members: list[Member],
    providers: dict[str, Provider],
    override: str | None = None,
    last_speaker: str | None = None,
) -> tuple[Member, Provider]:
    """Select Speaker: explicit override > strongest tier > rotation among equal tier."""
    if override:
        for m in members:
            if m.name.lower() == override.lower():
                return m, providers[m.name]
        raise ValueError(f"Speaker override '{override}' not found in members")

    top_tier = min(m.tier for m in members)
    top_members = [m for m in members if m.tier == top_tier]

    if len(top_members) == 1:
        m = top_members[0]
        return m, providers[m.name]

    # Rotate among equal-tier members
    if last_speaker:
        names = [m.name for m in top_members]
        if last_speaker in names:
            idx = names.index(last_speaker)
            m = top_members[(idx + 1) % len(top_members)]
            return m, providers[m.name]

    m = top_members[0]
    return m, providers[m.name]


class Parliament:
    """Main orchestrator. Stateless per call.

    Usage:
        p = Parliament(members=[...], providers={...})
        hansard = await p.ask("Should we use Postgres or Mongo?")
    """

    def __init__(
        self,
        members: list[Member],
        providers: dict[str, Provider],
        on_progress: ProgressCallback | None = None,
        speaker_override: str | None = None,
    ) -> None:
        if len(members) < 2:
            raise ValueError("Parliament requires at least 2 members")
        if len(members) > 3:
            raise ValueError("Parliament supports at most 3 members")

        self.members = [resolve_member_tier(m) for m in members]
        self.providers = providers
        self.on_progress = on_progress or _noop_progress
        self.speaker_override = speaker_override

        # Validate every member has a provider
        for m in self.members:
            if m.name not in self.providers:
                raise ValueError(f"No provider registered for member '{m.name}'")

    async def ask(
        self,
        question: str,
        last_speaker: str | None = None,
    ) -> Hansard:
        """Run a full parliamentary session. Returns a Hansard record."""
        start = time.monotonic()
        bill = Bill(content=question)

        # Phase 1: First Reading
        first_reading = await run_first_reading(
            bill=bill,
            members=self.members,
            providers=self.providers,
            on_progress=self.on_progress,
        )

        # Phase 2: Debate
        debate = await run_debate(
            bill=bill,
            members=self.members,
            providers=self.providers,
            first_reading=first_reading,
            on_progress=self.on_progress,
        )

        # Phase 3: Division
        speaker, speaker_provider = select_speaker(
            members=self.members,
            providers=self.providers,
            override=self.speaker_override,
            last_speaker=last_speaker,
        )

        synthesis = await run_division(
            bill=bill,
            members=self.members,
            debate_responses=debate,
            speaker=speaker,
            speaker_provider=speaker_provider,
            on_progress=self.on_progress,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        return Hansard(
            bill=bill,
            members=self.members,
            first_reading=first_reading,
            debate=debate,
            synthesis=synthesis,
            duration_ms=duration_ms,
        )

    def check_gaps(self) -> list[str]:
        """Return warning strings if tier gaps exist. Never blocks."""
        warnings = []
        if detect_gap(self.members):
            weakest = max(self.members, key=lambda m: m.tier)
            strongest = min(self.members, key=lambda m: m.tier)
            warnings.append(
                f"Large capability gap between {strongest.name} (tier {strongest.tier}) "
                f"and {weakest.name} (tier {weakest.tier}). "
                f"Debate quality is limited by the weakest member."
            )
        return warnings
