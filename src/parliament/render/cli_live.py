"""Rich-based live debate renderer for the `parliament ask` CLI.

Visibility model: per-response (panels pop in when each member's
.generate() returns) PLUS an animated spinner + elapsed timer per
pending member while we wait. The spinner runs inside a Rich Live
region so it animates without flooding scrollback; completed panels
are printed via console.print which Rich routes ABOVE the live region
so they persist as scrollback.

The Live region is only engaged on a real TTY. When stdout is piped,
captured by tests, or otherwise non-interactive, we degrade gracefully
to print-only output (no spinner) — same approach as Rich's own
console.status helper.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from parliament.core.types import ProgressEvent
from parliament.render import DebateRenderer

# Stage display metadata (header text + Rich color + emoji).
_STAGE_META = {
    "first_reading": ("First Reading", "blue", "📖"),
    "debate":        ("Debate",         "magenta", "🗣"),
    "division":      ("Division",       "yellow", "🗳"),
}

# Rotating per-member palette. Reserves: red=error, green=recommendation.
_MEMBER_COLORS = ["cyan", "magenta", "yellow"]


@dataclass
class _PendingMember:
    name: str
    color: str
    phase: str
    start_ts: float = field(default_factory=time.monotonic)


class RichLiveRenderer(DebateRenderer):
    """Stream stage headers and per-response panels to a Rich console.

    Adds a live spinner + elapsed timer per pending member so users see
    progress signal during blocking LLM calls.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._announced_stages: set[str] = set()
        self._member_color: dict[str, str] = {}
        self._pending: dict[str, _PendingMember] = {}
        self._live: Live | None = None

    # ---- DebateRenderer lifecycle ----

    def __enter__(self) -> "RichLiveRenderer":
        # Only engage Rich Live on a real TTY. On pipes / test buffers / dumb
        # terminals, Live's animation either does nothing or corrupts output.
        if self._console.is_terminal:
            self._live = Live(
                self._render_pending(),
                console=self._console,
                refresh_per_second=10,
                transient=True,  # leave a clean line behind when exiting
                auto_refresh=True,
            )
            self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._live is not None:
            try:
                self._live.__exit__(exc_type, exc_val, exc_tb)
            finally:
                self._live = None
        return None

    # ---- Event handling ----

    def emit(self, event: ProgressEvent) -> None:
        try:
            self._announce_stage(event.phase)
            color = self._color_for(event.member_name)

            if event.kind == "started":
                self._pending[event.member_name] = _PendingMember(
                    name=event.member_name,
                    color=color,
                    phase=event.phase,
                    start_ts=time.monotonic(),
                )
                self._refresh_live()
                return

            if event.kind == "completed":
                self._pending.pop(event.member_name, None)
                duration = (
                    f" [dim]({event.duration_ms / 1000:.1f}s)[/dim]"
                    if event.duration_ms is not None
                    else ""
                )

                if event.phase == "division" and event.synthesis is not None:
                    body = self._format_synthesis_body(event.synthesis)
                    title = f"{event.member_name} (Speaker){duration}"
                    panel = Panel(body, title=title, border_style=color)
                elif event.response is not None:
                    title_suffix = " (critique)" if event.phase == "debate" else ""
                    title = f"{event.member_name}{title_suffix}{duration}"
                    panel = Panel(
                        event.response.content, title=title, border_style=color
                    )
                else:
                    self._refresh_live()
                    return

                self._console.print(panel)
                self._refresh_live()
                return

            if event.kind == "failed":
                self._pending.pop(event.member_name, None)
                error = event.error or "unknown error"
                self._console.print(
                    Panel(
                        f"[red]{error}[/red]",
                        title=f"{event.member_name} — failed",
                        border_style="red",
                    )
                )
                self._refresh_live()
                return
        except Exception:  # pragma: no cover - never break a debate
            return

    # ---- internals ----

    def _color_for(self, member_name: str) -> str:
        if member_name not in self._member_color:
            idx = len(self._member_color) % len(_MEMBER_COLORS)
            self._member_color[member_name] = _MEMBER_COLORS[idx]
        return self._member_color[member_name]

    def _announce_stage(self, phase: str) -> None:
        if phase in self._announced_stages:
            return
        self._announced_stages.add(phase)
        label, color, emoji = _STAGE_META.get(phase, (phase.title(), "white", "•"))
        self._console.print()
        self._console.rule(f"[bold]{emoji}  {label}[/bold]", style=color)

    def _refresh_live(self) -> None:
        if self._live is not None:
            self._live.update(self._render_pending())

    def _render_pending(self) -> RenderableType:
        """Build the renderable shown inside the Live region.

        Returns an empty Text when no members are pending so the live region
        collapses to zero height between phases.
        """
        if not self._pending:
            return Text("")
        now = time.monotonic()
        table = Table.grid(padding=(0, 1))
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_column(justify="right", style="dim")
        for member in self._pending.values():
            elapsed = max(0.0, now - member.start_ts)
            spinner = Spinner("dots", style=member.color)
            name_text = Text(member.name, style=member.color)
            table.add_row(spinner, name_text, f"{elapsed:0.1f}s")
        return Group(table)

    @staticmethod
    def _format_synthesis_body(s: Any) -> str:
        """Render the Synthesis dataclass as a compact panel body."""
        chunks: list[str] = []
        if getattr(s, "consensus", ""):
            chunks.append(f"[bold cyan]CONSENSUS[/bold cyan]\n{s.consensus}")
        if getattr(s, "split", ""):
            chunks.append(f"[bold yellow]SPLIT[/bold yellow]\n{s.split}")
        if getattr(s, "risks", ""):
            chunks.append(f"[bold red]RISKS[/bold red]\n{s.risks}")
        if getattr(s, "recommendation", ""):
            chunks.append(f"[bold green]RECOMMENDATION[/bold green]\n{s.recommendation}")
        if not chunks:
            chunks.append(getattr(s, "raw", "") or "(empty synthesis)")
        return "\n\n".join(chunks)
