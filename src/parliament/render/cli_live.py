"""Rich-based live debate renderer for the `parliament ask` CLI."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel

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


class RichLiveRenderer(DebateRenderer):
    """Stream stage headers and per-response panels to a Rich console.

    Visibility model: per-response. Each member's full panel pops in when their
    .generate() returns. A dim 'thinking…' line is printed on 'started' so users
    see *something* happening while LLM calls are in flight.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._announced_stages: set[str] = set()
        self._member_color: dict[str, str] = {}

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

    def emit(self, event: ProgressEvent) -> None:
        try:
            self._announce_stage(event.phase)

            if event.kind == "started":
                color = self._color_for(event.member_name)
                self._console.print(
                    f"  [dim][{color}]{event.member_name}[/{color}] is thinking…[/dim]"
                )
                return

            if event.kind == "completed":
                color = self._color_for(event.member_name)
                duration = (
                    f" [dim]({event.duration_ms / 1000:.1f}s)[/dim]"
                    if event.duration_ms is not None
                    else ""
                )

                if event.phase == "division" and event.synthesis is not None:
                    s = event.synthesis
                    body = self._format_synthesis_body(s)
                    title = f"{event.member_name} (Speaker){duration}"
                    self._console.print(
                        Panel(body, title=title, border_style=color)
                    )
                    return

                if event.response is not None:
                    title_suffix = (
                        " (critique)" if event.phase == "debate" else ""
                    )
                    title = f"{event.member_name}{title_suffix}{duration}"
                    self._console.print(
                        Panel(event.response.content, title=title, border_style=color)
                    )
                return

            if event.kind == "failed":
                error = event.error or "unknown error"
                self._console.print(
                    Panel(
                        f"[red]{error}[/red]",
                        title=f"{event.member_name} — failed",
                        border_style="red",
                    )
                )
                return
        except Exception:  # pragma: no cover - belt-and-braces: never break a debate
            return

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
