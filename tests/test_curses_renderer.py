"""CursesLiveRenderer — minimal contract tests with a fake stdscr."""

from __future__ import annotations

from parliament.core.types import ProgressEvent, Response, Synthesis
from parliament.render import DebateRenderer, build_renderer
from parliament.render.tui_live import CursesLiveRenderer


class FakeStdscr:
    """Tiny stand-in for a curses window — captures addstr calls and refreshes."""

    def __init__(self, height: int = 24, width: int = 80) -> None:
        self._h = height
        self._w = width
        self.lines: list[tuple[int, int, str]] = []
        self.refresh_count = 0
        self.erase_count = 0

    def getmaxyx(self) -> tuple[int, int]:
        return self._h, self._w

    def erase(self) -> None:
        self.erase_count += 1
        self.lines = []  # erase resets the captured screen

    def refresh(self) -> None:
        self.refresh_count += 1

    def addnstr(self, y: int, x: int, text: str, n: int, attr: int = 0) -> None:
        self.lines.append((y, x, text[:n]))

    def addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        self.lines.append((y, x, text))

    def all_text(self) -> str:
        return "\n".join(t for _, _, t in self.lines)


def test_curses_renderer_is_a_debate_renderer():
    r = CursesLiveRenderer(stdscr=FakeStdscr())
    assert isinstance(r, DebateRenderer)


def test_build_renderer_returns_curses_for_tui():
    r = build_renderer(show_debate=True, mode="tui", stdscr=FakeStdscr())
    assert isinstance(r, CursesLiveRenderer)


def test_curses_renderer_refreshes_screen_on_emit():
    """Each emit must trigger a refresh so the user sees updates."""
    s = FakeStdscr()
    r = CursesLiveRenderer(stdscr=s)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    assert s.refresh_count >= 1


def test_curses_renderer_shows_phase_label_and_member_on_started():
    s = FakeStdscr()
    r = CursesLiveRenderer(stdscr=s)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    text = s.all_text()
    assert "First Reading" in text
    assert "Alpha" in text


def test_curses_renderer_shows_response_content_on_completed():
    s = FakeStdscr()
    r = CursesLiveRenderer(stdscr=s)
    response = Response(
        member_name="Alpha",
        content="The case for Postgres is strong.",
        phase="first_reading",
        duration_ms=500,
    )
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Alpha",
                kind="completed",
                response=response,
                duration_ms=500,
            )
        )
    text = s.all_text()
    assert "case for Postgres" in text


def test_curses_renderer_advances_through_all_phases():
    s = FakeStdscr()
    r = CursesLiveRenderer(stdscr=s)
    fr = Response(member_name="A", content="fr-content", phase="first_reading")
    dbt = Response(member_name="A", content="debate-content", phase="debate")
    synth = Synthesis(speaker_name="A", recommendation="ship it")
    with r:
        for ev in [
            ProgressEvent(phase="first_reading", member_name="A", kind="started"),
            ProgressEvent(phase="first_reading", member_name="A", kind="completed",
                          response=fr, duration_ms=10),
            ProgressEvent(phase="debate", member_name="A", kind="started"),
            ProgressEvent(phase="debate", member_name="A", kind="completed",
                          response=dbt, duration_ms=10),
            ProgressEvent(phase="division", member_name="A", kind="started"),
            ProgressEvent(phase="division", member_name="A", kind="completed",
                          synthesis=synth, duration_ms=10),
        ]:
            r.emit(ev)
    # The final visible state should be the Division phase with the synthesis.
    text = s.all_text()
    assert "Division" in text
    assert "ship it" in text


def test_curses_renderer_marks_failed_member():
    s = FakeStdscr()
    r = CursesLiveRenderer(stdscr=s)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Beta", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Beta",
                kind="failed",
                error="RuntimeError: synthetic failure",
                duration_ms=5,
            )
        )
    text = s.all_text().lower()
    # Some indication of failure must appear (not silently dropped).
    assert "fail" in text or "error" in text or "synthetic failure" in text


def test_curses_renderer_emit_never_raises_on_undersized_screen():
    """A 5x10 screen is absurd but emit() must still not crash."""
    s = FakeStdscr(height=5, width=10)
    r = CursesLiveRenderer(stdscr=s)
    response = Response(member_name="Alpha", content="long " * 200, phase="first_reading")
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Alpha",
                kind="completed",
                response=response,
                duration_ms=10,
            )
        )
    # Pass if nothing raised.
