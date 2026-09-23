"""Cancellation semantics for the parallel phases — see issue #34.

A cancelled member must abort the debate. A member that failed with a genuine
provider error must still degrade it. These two are easy to confuse because
``CancelledError`` is a ``BaseException``, not an ``Exception``.
"""

from __future__ import annotations

import asyncio

import pytest

from parliament.core.parliament import Parliament
from parliament.core.types import Bill, Hansard, Member, Response, Synthesis
from parliament.procedures.debate import run_debate
from parliament.procedures.first_reading import run_first_reading
from parliament.procedures.results import CANCELLED_MESSAGE, is_abort
from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider


def _noop(event):
    pass


class CancelledProvider(Provider):
    """Provider whose call is cancelled — as a cancel during generate() looks."""

    name = "cancelled"

    async def generate(self, prompt: str, system: str | None = None) -> str:
        raise asyncio.CancelledError


class SlowProvider(Provider):
    """Provider that never returns in time — used to exercise an outer timeout."""

    name = "slow"

    async def generate(self, prompt: str, system: str | None = None) -> str:
        await asyncio.sleep(30)
        return "too late"


class ErrorProvider(Provider):
    """Provider that fails with a real provider fault."""

    name = "error"

    async def generate(self, prompt: str, system: str | None = None) -> str:
        # Generic on purpose (TRY002 suppressed below): the code under test
        # has to cope with whatever a provider SDK raises, often bare Exception.
        raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")  # noqa: TRY002


class CancelOnCallProvider(Provider):
    """Succeeds until a chosen generate() call, which is cancelled."""

    name = "cancel-on-call"

    def __init__(self, fail_on_call: int) -> None:
        self._fail_on_call = fail_on_call
        self.calls = 0

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls += 1
        if self.calls == self._fail_on_call:
            raise asyncio.CancelledError
        return "CONSENSUS: ok\nSPLIT: none\nRISKS: low\nRECOMMENDATION: ship it"


MEMBERS = [
    Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
    Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
    Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
]

BILL = Bill(content="test question")


def _mock(name: str) -> MockProvider:
    return MockProvider(model=name, latency_ms=0)


def _readings(names: list[str]) -> list[Response]:
    return [
        Response(member_name=n, content=f"{n} analysis", phase="first_reading", duration_ms=1)
        for n in names
    ]


# ── The abort / degrade distinction ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc",
    [
        asyncio.CancelledError(),
        KeyboardInterrupt(),
        SystemExit(),
        GeneratorExit(),
    ],
)
def test_is_abort_true_for_non_exception_base_exceptions(exc):
    """Cancellation and interrupts abort the debate."""
    assert is_abort(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        Exception("429 quota exceeded"),
        TimeoutError("request timed out"),
        ConnectionRefusedError(),
        RuntimeError("HTTP 503"),
    ],
)
def test_is_abort_false_for_provider_failures(exc):
    """Provider faults degrade the debate rather than aborting it."""
    assert is_abort(exc) is False


# ── First Reading ──────────────────────────────────────────────────────────────


async def test_first_reading_cancelled_member_aborts():
    """One cancelled member aborts First Reading instead of degrading it."""
    providers = {"Alpha": _mock("mock-v1"), "Beta": CancelledProvider(), "Gamma": _mock("mock-v3")}

    with pytest.raises(asyncio.CancelledError):
        await run_first_reading(
            bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
        )


async def test_first_reading_cancellation_is_not_returned_as_a_response():
    """The exact bug from #34: a cancelled member never lands in the result list."""
    providers = {"Alpha": CancelledProvider(), "Beta": CancelledProvider(), "Gamma": CancelledProvider()}

    with pytest.raises(asyncio.CancelledError):
        await run_first_reading(
            bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
        )


async def test_first_reading_cancelled_member_reports_failure_event():
    """A cancelled member reports 'failed' so it doesn't sit at 'started' forever."""
    events = []
    providers = {"Alpha": _mock("mock-v1"), "Beta": CancelledProvider(), "Gamma": _mock("mock-v3")}

    with pytest.raises(asyncio.CancelledError):
        await run_first_reading(
            bill=BILL, members=MEMBERS, providers=providers, on_progress=events.append
        )

    failures = [e for e in events if e.kind == "failed"]
    assert [e.member_name for e in failures] == ["Beta"]
    assert failures[0].error == CANCELLED_MESSAGE


async def test_first_reading_provider_failure_still_degrades():
    """Contrast test: a genuine provider fault is not a cancellation."""
    providers = {"Alpha": _mock("mock-v1"), "Beta": ErrorProvider(), "Gamma": _mock("mock-v3")}

    responses = await run_first_reading(
        bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
    )

    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


async def test_first_reading_outer_timeout_aborts():
    """An enclosing timeout cancels the whole phase rather than shrinking it."""
    providers = {"Alpha": _mock("mock-v1"), "Beta": _mock("mock-v2"), "Gamma": SlowProvider()}

    # wait_for cancels the phase; it must not come back with a partial result.
    with pytest.raises((asyncio.CancelledError, TimeoutError)):
        await asyncio.wait_for(
            run_first_reading(
                bill=BILL, members=MEMBERS, providers=providers, on_progress=_noop
            ),
            timeout=0.05,
        )


# ── Debate ─────────────────────────────────────────────────────────────────────


async def test_debate_cancelled_member_aborts():
    """One cancelled member aborts Debate instead of degrading it."""
    providers = {"Alpha": _mock("mock-v1"), "Beta": CancelledProvider(), "Gamma": _mock("mock-v3")}

    with pytest.raises(asyncio.CancelledError):
        await run_debate(
            bill=BILL,
            members=MEMBERS,
            providers=providers,
            first_reading=_readings(["Alpha", "Beta", "Gamma"]),
            on_progress=_noop,
        )


async def test_debate_cancelled_member_reports_failure_event():
    events = []
    providers = {"Alpha": _mock("mock-v1"), "Beta": CancelledProvider(), "Gamma": _mock("mock-v3")}

    with pytest.raises(asyncio.CancelledError):
        await run_debate(
            bill=BILL,
            members=MEMBERS,
            providers=providers,
            first_reading=_readings(["Alpha", "Beta", "Gamma"]),
            on_progress=events.append,
        )

    failures = [e for e in events if e.kind == "failed"]
    assert [e.member_name for e in failures] == ["Beta"]
    assert failures[0].error == CANCELLED_MESSAGE


async def test_debate_provider_failure_still_degrades():
    """Contrast test: a genuine provider fault drops that member and continues."""
    providers = {"Alpha": _mock("mock-v1"), "Beta": ErrorProvider(), "Gamma": _mock("mock-v3")}

    responses = await run_debate(
        bill=BILL,
        members=MEMBERS,
        providers=providers,
        first_reading=_readings(["Alpha", "Beta", "Gamma"]),
        on_progress=_noop,
    )

    assert {r.member_name for r in responses} == {"Alpha", "Gamma"}


# ── Full pipeline ──────────────────────────────────────────────────────────────


async def test_parliament_ask_propagates_cancellation():
    """ask() does not turn a cancellation into a Hansard built from survivors."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
    ]
    providers = {"Alpha": _mock("mock-v1"), "Beta": CancelledProvider()}
    parliament = Parliament(members=members, providers=providers)

    with pytest.raises(asyncio.CancelledError):
        await parliament.ask("Should we use Postgres?")


async def test_parliament_ask_propagates_cancellation_from_division():
    """A cancel during Division aborts too — it isn't retried with another Speaker."""
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=1),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
    ]
    alpha = CancelOnCallProvider(fail_on_call=3)
    providers = {"Alpha": alpha, "Beta": _mock("mock-v2")}
    parliament = Parliament(members=members, providers=providers)

    with pytest.raises(asyncio.CancelledError):
        await parliament.ask("Can Division be cancelled?")

    assert alpha.calls == 3


# ── Hansard.degraded ───────────────────────────────────────────────────────────


async def test_hansard_not_degraded_when_all_members_respond():
    parliament = Parliament(
        members=MEMBERS,
        providers={m.name: _mock(m.model) for m in MEMBERS},
    )

    hansard = await parliament.ask("Should we use Postgres?")

    assert hansard.degraded is False


async def test_hansard_degraded_when_a_member_is_dropped():
    """A verdict from fewer members than configured is flagged as degraded."""
    parliament = Parliament(
        members=MEMBERS,
        providers={
            "Alpha": _mock("mock-v1"),
            "Beta": ErrorProvider(),
            "Gamma": _mock("mock-v3"),
        },
    )

    hansard = await parliament.ask("Should we use Postgres?")

    assert len(hansard.members) == 3
    assert len(hansard.first_reading) == 2
    assert hansard.degraded is True


def test_hansard_degraded_survives_json_roundtrip(make_hansard):
    hansard = make_hansard()
    hansard.degraded = True

    restored = Hansard.from_dict(hansard.to_dict())

    assert restored.degraded is True


def test_hansard_from_dict_without_degraded_key(make_hansard):
    """Hansards written before `degraded` existed still load."""
    data = make_hansard().to_dict()
    data.pop("degraded")

    assert Hansard.from_dict(data).degraded is False


def test_degraded_defaults_to_false():
    """The new field does not disturb the existing JSON shape."""
    hansard = Hansard(
        bill=Bill(content="q"),
        members=MEMBERS,
        first_reading=[],
        debate=[],
        synthesis=Synthesis(speaker_name="Alpha"),
    )

    assert hansard.degraded is False
    assert hansard.to_dict()["degraded"] is False
