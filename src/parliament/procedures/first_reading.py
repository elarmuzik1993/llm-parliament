"""First Reading — each member gives honest analysis in parallel."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from parliament.core.types import Bill, Member, ProgressEvent, Response
from parliament.providers.base import Provider
from parliament.providers.errors import format_provider_error

PROMPT_TEMPLATE = """\
You are one of {member_count} AI analysts deliberating on a technical decision.
Give your honest, thorough analysis of the following question.
Cover: pros, cons, tradeoffs, and your recommendation.
Be specific and practical.

Question: {question}"""


async def _read_one(
    bill: Bill,
    member: Member,
    provider: Provider,
    member_count: int,
    on_progress: Callable,
) -> Response:
    on_progress(
        ProgressEvent(
            phase="first_reading",
            member_name=member.name,
            kind="started",
        )
    )
    start = time.monotonic()
    try:
        prompt = PROMPT_TEMPLATE.format(
            member_count=member_count,
            question=bill.content,
        )
        content = await provider.generate(prompt)
        duration_ms = int((time.monotonic() - start) * 1000)
        response = Response(
            member_name=member.name,
            content=content,
            phase="first_reading",
            duration_ms=duration_ms,
        )
        on_progress(
            ProgressEvent(
                phase="first_reading",
                member_name=member.name,
                kind="completed",
                response=response,
                duration_ms=duration_ms,
            )
        )
        return response
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        on_progress(
            ProgressEvent(
                phase="first_reading",
                member_name=member.name,
                kind="failed",
                error=format_provider_error(exc),
                duration_ms=duration_ms,
            )
        )
        raise


async def run_first_reading(
    bill: Bill,
    members: list[Member],
    providers: dict[str, Provider],
    on_progress: Callable,
) -> list[Response]:
    """Run First Reading for all members in parallel."""
    tasks = [
        _read_one(bill, m, providers[m.name], len(members), on_progress)
        for m in members
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successes, track failures
    responses = []
    for r in results:
        if isinstance(r, Exception):
            # Degraded mode — skip failed member
            continue
        responses.append(r)

    if len(responses) < 2:
        failures = [
            f"  - {m.name}: {format_provider_error(r)}"
            for m, r in zip(members, results)
            if isinstance(r, Exception)
        ]
        raise RuntimeError(
            "Not enough members responded to continue "
            "(need at least 2 responses after First Reading).\n" + "\n".join(failures)
        )

    return responses
