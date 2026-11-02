"""Result partitioning shared by the parallel procedure phases.

First Reading and Debate both fan out to one coroutine per member with
``asyncio.gather(..., return_exceptions=True)``, then have to decide what the
results mean. That decision lives here so the two phases cannot drift apart —
see #34, where the equivalent change was applied to one of the two
``isinstance`` checks in each file and not the other.
"""

from __future__ import annotations

from parliament.core.types import Member, Response
from parliament.providers.errors import format_provider_error

CANCELLED_MESSAGE = "Cancelled — this member's work was stopped."


def is_abort(exc: BaseException) -> bool:
    """True for BaseExceptions that mean "stop the debate", not "drop a member".

    ``Exception`` covers provider faults — timeouts, quota exhaustion,
    connection refused. Losing a member to one of those is expected, and the
    parliament is built to carry on in degraded mode without them.

    Everything else means something *upstream* asked for the work to stop:
    ``CancelledError`` from a Ctrl-C, an enclosing ``asyncio.timeout``, or a
    client disconnecting, plus ``KeyboardInterrupt`` and ``SystemExit``. Those
    must not be quietly absorbed into "that member failed, carry on" — the
    debate has to stop too, or a timeout comes back looking like a confident
    verdict built from fewer members than the user configured.
    """
    return not isinstance(exc, Exception)


def partition_results(
    results: list[Response | BaseException],
    members: list[Member],
) -> tuple[list[Response], list[str], list[tuple[str, str]]]:
    """Split ``gather()`` results into responses, failure lines and failures.

    The failure lines are for an error message; the ``(member, error)`` pairs
    are for recording why a member dropped out (#95).

    Abort-worthy BaseExceptions are re-raised rather than returned, so one
    cancelled member aborts the debate instead of silently shrinking it.
    Genuine ``Exception`` failures are reported as formatted ``"  - name: msg"``
    lines and the phase continues in degraded mode, as it always has.
    """
    for result in results:
        if isinstance(result, BaseException) and is_abort(result):
            raise result

    responses: list[Response] = []
    failures: list[str] = []
    failed: list[tuple[str, str]] = []

    for member, result in zip(members, results):
        if isinstance(result, BaseException):
            error = format_provider_error(result)
            failures.append(f"  - {member.name}: {error}")
            failed.append((member.name, error))
            continue
        responses.append(result)

    return responses, failures, failed
