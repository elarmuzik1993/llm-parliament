"""`parliament mcp`: a stdio MCP server with one tool, `debate` (#9).

The shape follows the design note on #9 and its follow-up. The tool blocks for
the whole debate, reporting progress per phase. It returns a short result (the
summary, the verdict and the panel) and saves the full Hansard as JSON, because
the members' answers alone are larger than clients accept from a tool. Debates
run one at a time: OpenRouter reserves credit for every request in flight, and
parallel debates on a small balance fail with HTTP 402.
"""

from __future__ import annotations

import asyncio
import contextlib
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

# Bump on any change an agent parsing the result would notice.
SCHEMA_VERSION = 1

_PHASES = {"first_reading": "First Reading", "debate": "Debate", "division": "Division"}
# Moved to `summary`, or left to the saved file.
_NOT_IN_VERDICT = {"raw", "contested", "contested_on"}


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

    return server
