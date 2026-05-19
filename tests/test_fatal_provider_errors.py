"""Tests for resilient provider-error handling in First Reading and Debate."""

from __future__ import annotations

import pytest

from parliament.core.parliament import Parliament
from parliament.core.types import Bill, Member, Response
from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider
from parliament.procedures.first_reading import run_first_reading
from parliament.procedures.debate import run_debate


def _noop(event):
    pass


class ErrorProvider(Provider):
    """Provider that always raises the given exception."""

    name = "error"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def generate(self, prompt: str, system: str | None = None) -> str:
        raise self._exc


class FailOnCallProvider(Provider):
    """Provider that succeeds until a specific generate call."""

    name = "fail-on-call"

    def __init__(self, exc: Exception, fail_on_call: int) -> None:
        self._exc = exc
        self._fail_on_call = fail_on_call
        self.calls = 0

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls += 1
        if self.calls == self._fail_on_call:
            raise self._exc
        return "CONSENSUS: ok\nSPLIT: none\nRISKS: low\nRECOMMENDATION: ship it"


MEMBERS = [
    Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
    Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
    Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
]

BILL = Bill(content="test question")

_QUOTA_EXC = Exception("429 RESOURCE_EXHAUSTED: You exceeded your current quota, check billing")
_TIMEOUT_EXC = Exception("request timed out after 30s")
_SERVER_EXC = Exception("HTTP 503 Service Unavailable")


# ── First Reading ──────────────────────────────────────────────────────────────

async def test_first_reading_continues_on_fatal_error():
    """A quota-exhausted member is dropped; run continues with the 2 survivors."""
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_QUOTA_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    responses = await run_first_reading(
        bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
    )
    assert len(responses) == 2
    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


async def test_first_reading_fatal_error_emits_failed_progress():
    """Failure progress identifies the dropped member and formatted error."""
    events = []
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_QUOTA_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    await run_first_reading(
        bill=BILL, members=MEMBERS, providers=providers, on_progress=events.append
    )
    failures = [e for e in events if e.kind == "failed"]
    assert len(failures) == 1
    assert failures[0].member_name == "Beta"
    assert "quota" in failures[0].error.lower()


async def test_first_reading_continues_on_timeout():
    """A timed-out member is dropped; run continues with the 2 survivors."""
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_TIMEOUT_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    responses = await run_first_reading(
        bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
    )
    assert len(responses) == 2
    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


async def test_first_reading_continues_on_5xx():
    """A 5xx server error is dropped; run continues with the 2 survivors."""
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_SERVER_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    responses = await run_first_reading(
        bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
    )
    assert len(responses) == 2


# ── Debate ─────────────────────────────────────────────────────────────────────

def _make_readings(names: list[str]) -> list[Response]:
    return [
        Response(member_name=n, content=f"{n} analysis", phase="first_reading", duration_ms=100)
        for n in names
    ]


async def test_debate_continues_on_fatal_error():
    """A quota error during Debate drops that member and keeps 2 survivors."""
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_QUOTA_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    first_reading = _make_readings(["Alpha", "Beta", "Gamma"])
    responses = await run_debate(
        bill=BILL,
        members=MEMBERS,
        providers=providers,
        first_reading=first_reading,
        on_progress=_noop,
    )
    assert len(responses) == 2
    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


async def test_debate_continues_on_timeout():
    """A timeout during Debate drops that member; run continues with 2 survivors."""
    providers = {
        "Alpha": MockProvider(model="mock-v1", latency_ms=0),
        "Beta": ErrorProvider(_TIMEOUT_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    first_reading = _make_readings(["Alpha", "Beta", "Gamma"])
    responses = await run_debate(
        bill=BILL,
        members=MEMBERS,
        providers=providers,
        first_reading=first_reading,
        on_progress=_noop,
    )
    assert len(responses) == 2
    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


# ── Full Pipeline ──────────────────────────────────────────────────────────────

async def test_division_speaker_not_selected_from_failed_member():
    """Division chooses a survivor, not a stronger member dropped earlier."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=1),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
        Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
    ]
    providers = {
        "Alpha": ErrorProvider(_QUOTA_EXC),
        "Beta": MockProvider(model="mock-v2", latency_ms=0),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    parliament = Parliament(members=members, providers=providers)

    hansard = await parliament.ask("Should we use resilient debate?")

    assert {r.member_name for r in hansard.first_reading} == {"Beta", "Gamma"}
    assert {r.member_name for r in hansard.debate} == {"Beta", "Gamma"}
    assert hansard.synthesis.speaker_name in {"Beta", "Gamma"}


async def test_division_drops_failed_speaker_and_retries_with_survivor():
    """A Division failure drops that Speaker and retries with remaining survivors."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=1),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=2),
        Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
    ]
    alpha = FailOnCallProvider(_SERVER_EXC, fail_on_call=3)
    providers = {
        "Alpha": alpha,
        "Beta": MockProvider(model="mock-v2", latency_ms=0),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    parliament = Parliament(members=members, providers=providers)

    hansard = await parliament.ask("Can Division retry?")

    assert alpha.calls == 3
    assert hansard.synthesis.speaker_name == "Beta"


async def test_full_pipeline_one_fatal_one_transient_survivor():
    """Two dropped members leave too few survivors for a Hansard."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
        Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
    ]
    providers = {
        "Alpha": ErrorProvider(_QUOTA_EXC),
        "Beta": ErrorProvider(_TIMEOUT_EXC),
        "Gamma": MockProvider(model="mock-v3", latency_ms=0),
    }
    parliament = Parliament(members=members, providers=providers)

    with pytest.raises(RuntimeError, match="Not enough members responded to continue"):
        await parliament.ask("Can one member continue?")
