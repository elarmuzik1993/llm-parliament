"""Progress event protocol — emission shape from procedures."""

from __future__ import annotations

import pytest

from parliament.core.parliament import Parliament
from parliament.core.types import (
    Member,
    ProgressEvent,
    Response,
    Synthesis,
)
from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider


# ---------------- ProgressEvent dataclass shape ----------------


def test_progress_event_minimal_construction():
    """An event must require phase, member_name, and kind; payloads are optional."""
    event = ProgressEvent(phase="first_reading", member_name="Alpha", kind="started")

    assert event.phase == "first_reading"
    assert event.member_name == "Alpha"
    assert event.kind == "started"
    assert event.response is None
    assert event.synthesis is None
    assert event.error is None
    assert event.duration_ms is None


def test_progress_event_carries_response_payload():
    """A 'completed' first-reading/debate event should carry the Response."""
    resp = Response(member_name="Alpha", content="hello", phase="first_reading")
    event = ProgressEvent(
        phase="first_reading",
        member_name="Alpha",
        kind="completed",
        response=resp,
        duration_ms=1234,
    )

    assert event.response is resp
    assert event.duration_ms == 1234


def test_progress_event_carries_synthesis_payload():
    """A 'completed' division event should carry the Synthesis."""
    synth = Synthesis(speaker_name="Alpha", recommendation="ship it")
    event = ProgressEvent(
        phase="division",
        member_name="Alpha",
        kind="completed",
        synthesis=synth,
        duration_ms=99,
    )

    assert event.synthesis is synth


def test_progress_event_carries_error_on_failure():
    event = ProgressEvent(
        phase="debate",
        member_name="Beta",
        kind="failed",
        error="boom",
        duration_ms=42,
    )

    assert event.kind == "failed"
    assert event.error == "boom"


# ---------------- Procedure emissions (integration with mock parliament) ----------------


@pytest.fixture
def recorder():
    events: list[ProgressEvent] = []

    def record(event: ProgressEvent) -> None:
        events.append(event)

    record.events = events  # type: ignore[attr-defined]
    return record


@pytest.fixture
def mock_parliament_factory():
    def factory(on_progress, *, fail: str | None = None):
        members = [
            Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
            Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
            Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
        ]
        providers: dict[str, Provider] = {
            "Alpha": MockProvider(model="mock-v1", latency_ms=5),
            "Beta": MockProvider(model="mock-v2", latency_ms=5),
            "Gamma": MockProvider(model="mock-v3", latency_ms=5),
        }
        if fail:
            providers[fail] = _RaisingProvider(model="boom-v1")
        return Parliament(
            members=members,
            providers=providers,
            on_progress=on_progress,
        )

    return factory


class _RaisingProvider(Provider):
    """Provider that always raises — for failure-path tests."""

    name = "mock"

    def __init__(self, model: str) -> None:
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        raise RuntimeError("synthetic failure")


async def test_procedures_emit_started_then_completed_per_member(
    recorder, mock_parliament_factory
):
    """Each member should see a 'started' event and a 'completed' event for FR + Debate."""
    p = mock_parliament_factory(recorder)
    await p.ask("PostgreSQL or MongoDB?")

    fr = [e for e in recorder.events if e.phase == "first_reading"]
    dbt = [e for e in recorder.events if e.phase == "debate"]
    div = [e for e in recorder.events if e.phase == "division"]

    # First Reading: 3 started + 3 completed
    assert sorted(e.kind for e in fr) == ["completed"] * 3 + ["started"] * 3
    # Debate: 3 started + 3 completed
    assert sorted(e.kind for e in dbt) == ["completed"] * 3 + ["started"] * 3
    # Division: 1 started + 1 completed (single Speaker)
    assert sorted(e.kind for e in div) == ["completed", "started"]


async def test_first_reading_completed_event_carries_response(
    recorder, mock_parliament_factory
):
    p = mock_parliament_factory(recorder)
    await p.ask("Test question")

    completions = [
        e for e in recorder.events
        if e.phase == "first_reading" and e.kind == "completed"
    ]
    assert len(completions) == 3
    for e in completions:
        assert e.response is not None
        assert e.response.member_name == e.member_name
        assert e.response.phase == "first_reading"
        assert e.response.content  # non-empty
        assert e.duration_ms is not None and e.duration_ms >= 0


async def test_debate_completed_event_carries_response(
    recorder, mock_parliament_factory
):
    p = mock_parliament_factory(recorder)
    await p.ask("Test question")

    completions = [
        e for e in recorder.events
        if e.phase == "debate" and e.kind == "completed"
    ]
    assert len(completions) == 3
    for e in completions:
        assert e.response is not None
        assert e.response.phase == "debate"


async def test_division_completed_event_carries_synthesis(
    recorder, mock_parliament_factory
):
    p = mock_parliament_factory(recorder)
    await p.ask("Test question")

    completions = [
        e for e in recorder.events
        if e.phase == "division" and e.kind == "completed"
    ]
    assert len(completions) == 1
    e = completions[0]
    assert e.synthesis is not None
    assert e.synthesis.speaker_name == e.member_name
    assert e.synthesis.recommendation  # mock synthesis has one


async def test_failed_event_carries_error_message(recorder, mock_parliament_factory):
    """When a provider raises during First Reading, a 'failed' event must carry the error."""
    p = mock_parliament_factory(recorder, fail="Beta")
    await p.ask("Test question")  # 2 successes + 1 fail keeps the run alive

    failures = [
        e for e in recorder.events
        if e.kind == "failed" and e.member_name == "Beta"
    ]
    # At least one failure (Beta fails in First Reading; Beta is then dropped from Debate)
    assert failures
    assert all(e.error and "synthetic failure" in e.error for e in failures)
