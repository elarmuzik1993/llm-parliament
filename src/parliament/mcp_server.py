"""`parliament mcp`: a stdio MCP server with two tools, `debate` (#9) and `ask` (#99).

The shape of `debate` follows the design note on #9 and its follow-up. The tool
blocks for the whole debate, reporting progress per phase. It returns a short
result (the summary, the verdict and the panel) and saves the full Hansard as
JSON, because the members' answers alone are larger than clients accept from a
tool. Debates run one at a time: OpenRouter reserves credit for every request
in flight, and parallel debates on a small balance fail with HTTP 402.

`ask` is one call to one configured model, for a quick second opinion. It does
not queue behind a debate: one extra request in flight is not what exhausts the
credit, and an agent should not wait minutes for a seconds-long answer.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from parliament import __version__
from parliament.config import HANSARDS_DIR
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard, Member, ProgressEvent
from parliament.providers.base import Provider
from parliament.providers.errors import format_provider_error

# Bump on any change an agent parsing the result would notice.
SCHEMA_VERSION = 1

_PHASES = {"first_reading": "First Reading", "debate": "Debate", "division": "Division"}
# Moved to `summary`, or left to the saved file.
_NOT_IN_VERDICT = {"raw", "contested", "contested_on"}

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
        "little. For a consequential decision with real trade-offs, use debate "
        "instead. Returns the answer and the path of the saved record."
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


def save_ask_json(record: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}-{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


async def _heartbeat(report: Callable[[str], Awaitable[None]], every_s: float) -> None:
    while True:
        await asyncio.sleep(every_s)
        await report("Waiting for the previous debate to finish")


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

    @server.tool(name="debate", description=_describe(members))
    async def debate(question: str, ctx: Context) -> dict[str, Any]:
        sent = 0

        async def report(message: str) -> None:
            nonlocal sent
            sent += 1  # progress must rise with every report
            await ctx.report_progress(sent, message=message)

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
            return await _run(question, report)
        finally:
            lock.release()

    async def _run(question: str, report: Callable[[str], Awaitable[None]]) -> dict[str, Any]:
        # Progress events arrive through a plain callback; one sender keeps
        # the notifications in order.
        events: asyncio.Queue[str | None] = asyncio.Queue()

        def on_progress(event: ProgressEvent) -> None:
            if event.kind in ("completed", "failed"):
                verb = "done" if event.kind == "completed" else "failed"
                events.put_nowait(f"{_PHASES.get(event.phase, event.phase)}: {event.member_name} {verb}")

        async def send() -> None:
            while (message := await events.get()) is not None:
                await report(message)

        sender = asyncio.create_task(send())
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
        finally:
            events.put_nowait(None)
            await sender
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
        path = save_ask_json(record, save_dir / "asks")
        return {
            "schema": SCHEMA_VERSION,
            "member": who.name,
            "provider": who.provider_name,
            "model": who.model,
            "answer": answer,
            "duration_ms": duration_ms,
            "record_path": str(path),
        }

    return server
