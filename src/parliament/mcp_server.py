"""`parliament mcp`: a stdio MCP server with three tools, `debate` (#9), `ask` and `consult` (#99).

The shape of `debate` follows the design note on #9 and its follow-up. The tool
blocks for the whole debate, reporting progress per phase. It returns a short
result (the summary, the verdict and the panel) and saves the full Hansard as
JSON, because the members' answers alone are larger than clients accept from a
tool. Debates run one at a time: OpenRouter reserves credit for every request
in flight, and parallel debates on a small balance fail with HTTP 402.

`ask` is one call to one configured model, for a quick second opinion. It does
not queue behind a debate: one extra request in flight is not what exhausts the
credit, and an agent should not wait minutes for a seconds-long answer.

`consult` is First Reading alone: independent answers from several panel
members in parallel, with no critique and no Speaker. It queues behind a debate
like another debate would, because it puts as many requests in flight at once.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from parliament import __version__
from parliament.config import HANSARDS_DIR
from parliament.core.parliament import Parliament, failure_warnings
from parliament.core.types import Bill, Hansard, Member, ProgressEvent
from parliament.procedures.first_reading import run_first_reading
from parliament.providers.base import Provider
from parliament.providers.errors import format_provider_error

# Bump on any change an agent parsing the result would notice.
SCHEMA_VERSION = 1

_PHASES = {"first_reading": "First Reading", "debate": "Debate", "division": "Division"}
# Moved to `summary`, or left to the saved file.
_NOT_IN_VERDICT = {"raw", "contested", "contested_on"}

# Clients limit tool output; the saved record has the full text.
ANSWER_CHARS = 8000

# The question goes to the model as written; this is the only framing.
ASK_SYSTEM = (
    "A coding agent is consulting you for a second opinion. Answer directly and "
    "specifically; state your recommendation and the main reasons. Say when you "
    "are unsure."
)


def is_mock_only(members: list[Member]) -> bool:
    """A mock panel gives fake verdicts; an agent must not mistake them for advice."""
    return all(m.provider_name == "mock" for m in members)


def build_result(hansard: Hansard, hansard_path: Path) -> dict[str, Any]:
    """The tool's answer: flags first, then the verdict, then where the rest is."""
    data = hansard.to_dict()
    synthesis = data["synthesis"]
    positions = [
        {
            "member": r["member_name"],
            "stance": (r["position"] or {}).get("stance"),
            "changed_mind": (r["position"] or {}).get("changed_mind"),
        }
        for r in data["debate"]
    ]
    return {
        "schema": SCHEMA_VERSION,
        "summary": {
            "contested": synthesis["contested"],
            "contested_on": synthesis["contested_on"],
            "degraded": data["degraded"],
            "warnings": data["warnings"],
            "positions": positions,
        },
        "verdict": {k: v for k, v in synthesis.items() if k not in _NOT_IN_VERDICT},
        "members": data["members"],
        "hansard_path": str(hansard_path),
    }


def save_hansard_json(hansard: Hansard, directory: Path = HANSARDS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}-{hansard.id[:8]}.json"
    path.write_text(hansard.to_json(), encoding="utf-8")
    return path


def _describe(members: list[Member]) -> str:
    calls = len(members) * 2 + 1
    names = ", ".join(f"{m.name} ({m.model})" for m in members)
    return (
        "Convene a parliament of LLMs on a decision: each member answers, critiques "
        "the others, and a Speaker writes the verdict. Use it for a consequential "
        "choice with real trade-offs (architecture, a risky migration), not for "
        f"facts or small edits. Each call makes {calls} model calls to the panel "
        f"({names}), costs money and takes one to three minutes. Returns "
        "summary.contested (whether the members still disagree, null if unknown), "
        "summary.contested_on, the verdict, and the path of the full saved record."
    )


def _describe_ask(members: list[Member], outside: tuple[Member, Provider] | None) -> str:
    names = [f"{m.name} ({m.model})" for m in members]
    if outside is not None:
        names.append(f"{outside[0].name} ({outside[0].model}, the outside Speaker)")
    return (
        "Ask ONE model directly for a second opinion, with no debate. It makes one "
        "model call, which costs money and takes seconds. "
        f"member is one of: {', '.join(names)}. "
        "The model cannot see your files or this conversation, so put all the "
        "context it needs in the question. Asking the same model you run on adds "
        "little. To compare several models' answers, use consult. For a "
        "consequential decision with real trade-offs, use debate instead. Returns "
        "the answer and the path of the saved record."
    )


def _describe_consult(members: list[Member]) -> str:
    names = ", ".join(f"{m.name} ({m.model})" for m in members)
    return (
        "Get independent answers from several panel members in parallel, with no "
        "debate and no verdict. By default it asks the whole panel "
        f"({names}), which makes {len(members)} model calls; members narrows it "
        "to two or more of those names, one call each. It costs money, takes under "
        "a minute, and waits for a running debate to finish. The models cannot see "
        "your files or this conversation, so put all the context they need in the "
        "question. Returns each member's answer and self-reported stance. Nothing "
        "judges whether they agree: compare the stances yourself, and use debate "
        "if they disagree on a consequential decision."
    )


def _askable(
    members: list[Member],
    providers: dict[str, Provider],
    outside: tuple[Member, Provider] | None,
) -> dict[str, tuple[Member, Provider]]:
    """Name (lower case) to member and provider; a panel member wins a clash."""
    found: dict[str, tuple[Member, Provider]] = {}
    if outside is not None:
        found[outside[0].name.lower()] = outside
    for m in members:
        found[m.name.lower()] = (m, providers[m.name])
    return found


def _consulted(
    names: list[str] | None,
    members: list[Member],
    outside: tuple[Member, Provider] | None,
) -> list[Member]:
    """The panel members named, once each and in panel order; None is the whole panel."""
    if names is None:
        chosen = list(members)
    else:
        panel = {m.name.lower() for m in members}
        unknown = [n for n in names if n.strip().lower() not in panel]
        if unknown:
            message = (
                f"No panel member named {', '.join(repr(n) for n in unknown)}. "
                f"Consult two or more of: {', '.join(m.name for m in members)}"
            )
            if outside is not None and any(
                n.strip().lower() == outside[0].name.lower() for n in unknown
            ):
                message += (
                    f". {outside[0].name} is the outside Speaker, not a panel "
                    "member; ask it with ask"
                )
            raise ToolError(message)
        wanted = {n.strip().lower() for n in names}
        chosen = [m for m in members if m.name.lower() in wanted]
    if len(chosen) < 2:
        raise ToolError(
            "consult needs at least two different panel members; to ask one model, use ask"
        )
    return chosen


def save_record_json(record: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}-{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


async def _heartbeat(report: Callable[[str], Awaitable[None]], every_s: float) -> None:
    while True:
        await asyncio.sleep(every_s)
        await report("Waiting for the previous debate to finish")


def _reporter(ctx: Context) -> Callable[[str], Awaitable[None]]:
    sent = 0

    async def report(message: str) -> None:
        nonlocal sent
        sent += 1  # progress must rise with every report
        await ctx.report_progress(sent, message=message)

    return report


@contextlib.asynccontextmanager
async def _member_progress(
    report: Callable[[str], Awaitable[None]],
) -> AsyncIterator[Callable[[ProgressEvent], None]]:
    """An on_progress callback that reports each member's answer, done or failed."""
    # Progress events arrive through a plain callback; one sender keeps the
    # notifications in order.
    events: asyncio.Queue[str | None] = asyncio.Queue()

    def on_progress(event: ProgressEvent) -> None:
        if event.kind in ("completed", "failed"):
            verb = "done" if event.kind == "completed" else "failed"
            events.put_nowait(f"{_PHASES.get(event.phase, event.phase)}: {event.member_name} {verb}")

    async def send() -> None:
        while (message := await events.get()) is not None:
            await report(message)

    sender = asyncio.create_task(send())
    try:
        yield on_progress
    finally:
        events.put_nowait(None)
        await sender


def create_server(
    members: list[Member],
    providers: dict[str, Provider],
    *,
    outside_speaker: tuple[Member, Provider] | None = None,
    speaker_override: str | None = None,
    save_dir: Path = HANSARDS_DIR,
    heartbeat_s: float = 30.0,
) -> MCPServer:
    # WARNING, not the SDK's INFO: at INFO every provider request is logged to
    # the client's stderr, one line per HTTP call.
    server = MCPServer("parliament", version=__version__, log_level="WARNING")
    lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def queued(report: Callable[[str], Awaitable[None]]) -> AsyncIterator[None]:
        """Hold `lock` for the block, one parallel fan-out at a time."""
        # Keep a queued call visibly alive, so idle limits don't cut it off.
        if lock.locked():
            await report("Waiting for the previous debate to finish")
        beat = asyncio.create_task(_heartbeat(report, heartbeat_s))
        try:
            await lock.acquire()
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
        try:
            yield
        finally:
            lock.release()

    @server.tool(name="debate", description=_describe(members))
    async def debate(question: str, ctx: Context) -> dict[str, Any]:
        report = _reporter(ctx)
        async with queued(report), _member_progress(report) as on_progress:
            parliament = Parliament(
                members,
                providers,
                on_progress=on_progress,
                speaker_override=speaker_override,
                outside_speaker=outside_speaker,
            )
            try:
                hansard = await parliament.ask(question)
            except Exception as exc:  # a provider fault the debate could not absorb
                raise ToolError(f"The debate failed: {exc}") from exc
        return build_result(hansard, save_hansard_json(hansard, save_dir))

    askable = _askable(members, providers, outside_speaker)

    # Registered after `debate`, so `debate` stays the first tool listed.
    @server.tool(name="ask", description=_describe_ask(members, outside_speaker))
    async def ask(member: str, question: str) -> dict[str, Any]:
        # No `lock`: an ask must not wait minutes behind a running debate.
        found = askable.get(member.strip().lower())
        if found is None:
            valid = ", ".join(m.name for m, _ in askable.values())
            raise ToolError(f"No member named {member!r}. Ask one of: {valid}")
        who, provider = found
        started = time.perf_counter()
        try:
            answer = await provider.generate(question, system=ASK_SYSTEM)
        except Exception as exc:  # a provider fault; cancellation still propagates
            raise ToolError(f"{who.name} failed: {format_provider_error(exc)}") from exc
        if not answer:
            raise ToolError(f"{who.name} returned no text")
        duration_ms = round((time.perf_counter() - started) * 1000)
        record = {
            "schema": SCHEMA_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "member": who.name,
            "provider": who.provider_name,
            "model": who.model,
            "question": question,
            "answer": answer,
            "duration_ms": duration_ms,
        }
        path = save_record_json(record, save_dir / "asks")
        return {
            "schema": SCHEMA_VERSION,
            "member": who.name,
            "provider": who.provider_name,
            "model": who.model,
            "answer": answer,
            "duration_ms": duration_ms,
            "record_path": str(path),
        }

    by_name = {m.name: m for m in members}

    # Registered after `ask`: debate, ask, consult.
    @server.tool(name="consult", description=_describe_consult(members))
    async def consult(
        question: str, ctx: Context, members: list[str] | None = None
    ) -> dict[str, Any]:
        # A bad name is refused before the call queues behind a debate.
        chosen = _consulted(members, list(by_name.values()), outside_speaker)
        failures: list[tuple[str, str]] = []
        report = _reporter(ctx)
        async with queued(report), _member_progress(report) as on_progress:
            try:
                responses = await run_first_reading(
                    Bill(content=question),
                    chosen,
                    providers,
                    on_progress,
                    failures_out=failures,
                )
            except Exception as exc:  # too few answers; cancellation still propagates
                raise ToolError(f"The consultation failed: {exc}") from exc
        # No `contested`: stances are self-reported, never compared here (#73).
        positions = [
            {"member": r.member_name, "stance": r.position.stance if r.position else None}
            for r in responses
        ]
        answers: list[dict[str, Any]] = [
            {
                "member": r.member_name,
                "provider": by_name[r.member_name].provider_name,
                "model": by_name[r.member_name].model,
                "answer": r.content,
                "duration_ms": r.duration_ms,
            }
            for r in responses
        ]
        warnings = [asdict(w) for w in failure_warnings("First Reading", failures)]
        degraded = len(responses) < len(chosen)
        record = {
            "schema": SCHEMA_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "question": question,
            "members": [m.name for m in chosen],
            "positions": positions,
            "answers": answers,
            "degraded": degraded,
            "warnings": warnings,
        }
        path = save_record_json(record, save_dir / "consults")
        return {
            "schema": SCHEMA_VERSION,
            "positions": positions,
            "answers": [
                {
                    **{k: a[k] for k in ("member", "provider", "model")},
                    "answer": a["answer"][:ANSWER_CHARS],
                    "truncated": len(a["answer"]) > ANSWER_CHARS,
                    "duration_ms": a["duration_ms"],
                }
                for a in answers
            ],
            "degraded": degraded,
            "warnings": warnings,
            "record_path": str(path),
        }

    return server
