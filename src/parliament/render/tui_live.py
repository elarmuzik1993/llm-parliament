"""Curses live debate renderer for the interactive TUI.

Maintains per-member status state across events and redraws the curses screen
on every emit. Bounded to whatever (height, width) the terminal currently is —
overflow is silently truncated rather than crashed, since this draws inside an
already-running TUI session.
"""

from __future__ import annotations

import curses
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from parliament.core.types import ProgressEvent, Synthesis
from parliament.render import DebateRenderer

_PHASE_LABELS = {
    "first_reading": "First Reading",
    "debate":        "Debate",
    "division":      "Division",
}

_STATE_GLYPH = {
    "started":   "|",
    "completed": "✓",
    "failed":    "✗",
}

_SPINNER_FRAMES = ("|", "/", "-", "\\")

_COLOR_PAIR = {
    "title": 1,
    "phase": 2,
    "pending": 3,
    "done": 4,
    "failed": 5,
    "dim": 6,
}


@dataclass
class _MemberStatus:
    name: str
    state: str = "started"
    duration_ms: int | None = None
    start_ts: float = field(default_factory=time.monotonic)


@dataclass
class _PhaseState:
    phase: str
    members: dict[str, _MemberStatus] = field(default_factory=dict)
    last_content: str = ""  # most recent completed response/synthesis text


class CursesLiveRenderer(DebateRenderer):
    """Live debate view that draws into an existing curses window.

    All curses drawing happens on the main thread via redraw(), which is
    called from the _run_cancellable_debate polling loop. The worker thread
    only mutates state via emit(); it never touches the curses window.
    """

    def __init__(self, stdscr: Any, show_responses: bool = True) -> None:
        self._stdscr = stdscr
        self._show_responses = show_responses
        self._current_phase: str | None = None
        self._phases: dict[str, _PhaseState] = {}
        self._lock = RLock()
        self._colors_ready = False

    # ---- DebateRenderer ----

    def __enter__(self) -> "CursesLiveRenderer":
        self._init_colors()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def emit(self, event: ProgressEvent) -> None:
        try:
            with self._lock:
                self._update_state(event)
        except Exception:  # pragma: no cover - never break the debate
            return

    def redraw(self) -> None:
        """Refresh the screen. Must be called from the main (curses) thread."""
        try:
            self._redraw()
        except Exception:  # pragma: no cover
            return

    # ---- internals ----

    def _init_colors(self) -> None:
        try:
            if not curses.has_colors():
                return
            curses.start_color()
            try:
                curses.use_default_colors()
                background = -1
            except curses.error:
                background = curses.COLOR_BLACK
            curses.init_pair(_COLOR_PAIR["title"], curses.COLOR_CYAN, background)
            curses.init_pair(_COLOR_PAIR["phase"], curses.COLOR_MAGENTA, background)
            curses.init_pair(_COLOR_PAIR["pending"], curses.COLOR_YELLOW, background)
            curses.init_pair(_COLOR_PAIR["done"], curses.COLOR_GREEN, background)
            curses.init_pair(_COLOR_PAIR["failed"], curses.COLOR_RED, background)
            curses.init_pair(_COLOR_PAIR["dim"], curses.COLOR_BLUE, background)
            self._colors_ready = True
        except (AttributeError, curses.error):
            self._colors_ready = False

    def _update_state(self, event: ProgressEvent) -> None:
        self._current_phase = event.phase
        ps = self._phases.setdefault(event.phase, _PhaseState(phase=event.phase))
        ms = ps.members.setdefault(event.member_name, _MemberStatus(name=event.member_name))
        ms.state = event.kind
        if event.kind == "started":
            ms.start_ts = time.monotonic()
        if event.duration_ms is not None:
            ms.duration_ms = event.duration_ms
        if event.kind == "completed":
            if event.response is not None:
                ps.last_content = event.response.content
            elif event.synthesis is not None:
                ps.last_content = self._render_synthesis(event.synthesis)
        elif event.kind == "failed":
            ps.last_content = f"FAILED: {event.error or 'unknown error'}"

    def _redraw(self) -> None:
        s = self._stdscr
        height, width = s.getmaxyx()
        s.erase()

        cancel_hint = "Press q, Esc, or Ctrl+C to cancel"

        if not self._show_responses:
            # Minimal waiting screen — live debate view is OFF
            self._safe_addstr(0, 0, "Parliament — running debate", self._attr("title", curses.A_BOLD), width)
            with self._lock:
                phase = self._current_phase or "first_reading"
            label = _PHASE_LABELS.get(phase, phase.title())
            self._safe_addstr(2, 0, f"Phase: {label}…", self._attr("phase", curses.A_DIM), width)
            self._safe_addstr(max(0, height - 1), 0, cancel_hint, self._attr("dim", curses.A_DIM), width)
            s.refresh()
            return

        with self._lock:
            phase = self._current_phase or "first_reading"
            ps = self._phases.get(phase)
            snapshot = list(ps.members.values()) if ps else []
            last_content = ps.last_content if ps else ""

        # Title row
        self._safe_addstr(0, 0, "Parliament — live debate", self._attr("title", curses.A_BOLD), width)

        # Phase header
        label = _PHASE_LABELS.get(phase, phase.title())
        self._safe_addstr(2, 0, f"Phase: {label}", self._attr("phase", curses.A_BOLD), width)

        # Per-member status rows for the current phase
        row = 4
        now = time.monotonic()
        if snapshot:
            for member in snapshot:
                duration = (
                    f"{member.duration_ms / 1000:.1f}s"
                    if member.duration_ms is not None and member.state != "started"
                    else f"{max(0.0, now - member.start_ts):0.1f}s"
                )
                state_label = (
                    "failed" if member.state == "failed" else
                    "done" if member.state == "completed" else
                    "thinking"
                )
                glyph = (
                    _SPINNER_FRAMES[int(now * 8) % len(_SPINNER_FRAMES)]
                    if member.state == "started"
                    else _STATE_GLYPH.get(member.state, "?")
                )
                line = f"  {glyph} {member.name:<18} {state_label:<10} {duration}"
                attr = self._attr("pending", curses.A_DIM) if member.state == "started" else self._attr("done", curses.A_NORMAL)
                if member.state == "failed":
                    attr = self._attr("failed", curses.A_BOLD)
                self._safe_addstr(row, 0, line, attr, width)
                row += 1
                if row >= height - 4:
                    break

        # Last completed content (response or synthesis)
        if last_content:
            content_top = max(row + 1, height - 10)
            content_top = min(content_top, height - 2)
            self._safe_addstr(content_top, 0, "── Last response ──", self._attr("dim", curses.A_DIM), width)
            import textwrap
            wrapped: list[str] = []
            for ln in last_content.splitlines():
                if not ln.strip():
                    wrapped.append("")
                elif len(ln) < width - 1:
                    wrapped.append(ln)
                else:
                    wrapped.extend(textwrap.wrap(ln, width=width - 1, break_long_words=True))
            visible = max(1, height - content_top - 2)
            for offset, line in enumerate(wrapped[:visible]):
                self._safe_addstr(content_top + 1 + offset, 0, line, curses.A_NORMAL, width)

        # Footer hint
        self._safe_addstr(max(0, height - 1), 0, f"Working… {cancel_hint}", self._attr("dim", curses.A_DIM), width)

        s.refresh()


    def _attr(self, role: str, fallback: int) -> int:
        if not self._colors_ready:
            return fallback
        try:
            return fallback | curses.color_pair(_COLOR_PAIR[role])
        except (KeyError, curses.error):
            return fallback

    def _safe_addstr(self, y: int, x: int, text: str, attr: int, width: int) -> None:
        """Write text bounded by the screen width, ignoring out-of-range rows."""
        height, _ = self._stdscr.getmaxyx()
        if y < 0 or y >= height:
            return
        max_len = max(0, width - x - 1)
        if max_len <= 0:
            return
        snippet = text[:max_len]
        try:
            # Prefer addnstr for a hard length cap when available
            self._stdscr.addnstr(y, x, snippet, max_len, attr)
        except (TypeError, AttributeError):
            try:
                self._stdscr.addstr(y, x, snippet, attr)
            except curses.error:  # pragma: no cover - last-row last-col edge case
                return
        except curses.error:  # pragma: no cover
            return

    @staticmethod
    def _render_synthesis(s: Synthesis) -> str:
        chunks: list[str] = []
        if s.consensus:
            chunks.append(f"CONSENSUS\n{s.consensus}")
        if s.split:
            chunks.append(f"SPLIT\n{s.split}")
        if s.risks:
            chunks.append(f"RISKS\n{s.risks}")
        if s.recommendation:
            chunks.append(f"RECOMMENDATION\n{s.recommendation}")
        return "\n\n".join(chunks) or (s.raw or "(empty synthesis)")
