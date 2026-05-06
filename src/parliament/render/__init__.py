"""Renderer abstraction for the live debate view.

The DebateRenderer protocol decouples Parliament.ask from any specific UI.
Concrete implementations:

  - SilentRenderer:    no-op, used when --no-show-debate.
  - RichLiveRenderer:  Rich-based, used by the `parliament ask` CLI command.
  - CursesLiveRenderer: curses-based, used by the interactive TUI.

A renderer is a context manager so it owns its own setup/teardown
(opening a Rich Live, refreshing curses, etc.). Procedures call .emit(event)
via Parliament.on_progress as work advances.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from parliament.core.types import ProgressEvent


class DebateRenderer(ABC):
    """Context-managed sink for ProgressEvent.

    Subclass and implement emit(). Override __enter__ / __exit__ if your
    renderer needs to hold an external resource (Live, curses screen).
    """

    def __enter__(self) -> "DebateRenderer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    @abstractmethod
    def emit(self, event: ProgressEvent) -> None:
        """Receive an event from a procedure. Must not raise."""
        ...


class SilentRenderer(DebateRenderer):
    """No-op renderer used when --show-debate is off."""

    def emit(self, event: ProgressEvent) -> None:  # noqa: D401
        return None


def build_renderer(
    *,
    show_debate: bool,
    mode: str,
    console: Any | None = None,
    stdscr: Any | None = None,
) -> DebateRenderer:
    """Pick the right renderer for the active interface.

    mode: "cli" (Rich) | "tui" (curses).
    """
    if not show_debate:
        return SilentRenderer()
    if mode == "cli":
        from parliament.render.cli_live import RichLiveRenderer
        return RichLiveRenderer(console=console)
    if mode == "tui":
        from parliament.render.tui_live import CursesLiveRenderer
        return CursesLiveRenderer(stdscr=stdscr)
    raise ValueError(f"Unknown renderer mode: {mode!r} (expected 'cli' or 'tui')")


__all__ = [
    "DebateRenderer",
    "SilentRenderer",
    "build_renderer",
    "RichLiveRenderer",
]


# Re-export RichLiveRenderer at the package level for convenient testing.
def __getattr__(name: str):  # pragma: no cover - thin re-export shim
    if name == "RichLiveRenderer":
        from parliament.render.cli_live import RichLiveRenderer
        return RichLiveRenderer
    if name == "CursesLiveRenderer":
        from parliament.render.tui_live import CursesLiveRenderer
        return CursesLiveRenderer
    raise AttributeError(name)
