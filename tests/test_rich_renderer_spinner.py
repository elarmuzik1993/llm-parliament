"""RichLiveRenderer — animated spinner + elapsed timer behavior.

Path 1 of the live-debate-visibility plan: while members are 'thinking',
the renderer shows a spinner row + elapsed seconds per pending member,
so the user sees the system is working even though providers are blocking.

These tests are state-and-renderable based: they don't try to drive Rich's
real Live (which doesn't refresh on a non-TTY recording console), so they
exercise the pending-set bookkeeping and the renderable output directly.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from parliament.core.types import ProgressEvent, Response
from parliament.render.cli_live import RichLiveRenderer


@pytest.fixture
def recording_console():
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120, record=True), buf


def _render_to_text(renderable, width: int = 120) -> str:
    buf = io.StringIO()
    Console(file=buf, force_terminal=False, width=width).print(renderable)
    return buf.getvalue()


# ---------- Pending-set bookkeeping ----------


def test_started_event_adds_member_to_pending():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    assert "Alpha" in r._pending


def test_completed_event_removes_member_from_pending():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    response = Response(
        member_name="Alpha", content="x", phase="first_reading", duration_ms=100
    )
    r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    r.emit(
        ProgressEvent(
            phase="first_reading",
            member_name="Alpha",
            kind="completed",
            response=response,
            duration_ms=100,
        )
    )
    assert "Alpha" not in r._pending


def test_failed_event_removes_member_from_pending():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    r.emit(ProgressEvent(phase="first_reading", member_name="Beta", kind="started"))
    r.emit(
        ProgressEvent(
            phase="first_reading",
            member_name="Beta",
            kind="failed",
            error="boom",
            duration_ms=10,
        )
    )
    assert "Beta" not in r._pending


def test_concurrent_pending_members_tracked_independently():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    r.emit(ProgressEvent(phase="first_reading", member_name="Beta", kind="started"))
    r.emit(ProgressEvent(phase="first_reading", member_name="Gamma", kind="started"))
    assert set(r._pending.keys()) == {"Alpha", "Beta", "Gamma"}

    r.emit(
        ProgressEvent(
            phase="first_reading",
            member_name="Beta",
            kind="completed",
            response=Response(member_name="Beta", content="y", phase="first_reading"),
            duration_ms=200,
        )
    )
    assert set(r._pending.keys()) == {"Alpha", "Gamma"}


# ---------- Renderable for the spinner panel ----------


def test_pending_renderable_empty_when_no_members_pending():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    text = _render_to_text(r._render_pending())
    # No member names, just the formatted empty renderable. Output should be very short.
    assert text.strip() == ""


def test_pending_renderable_includes_each_member_name():
    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    r.emit(ProgressEvent(phase="first_reading", member_name="Beta", kind="started"))
    text = _render_to_text(r._render_pending())
    assert "Alpha" in text
    assert "Beta" in text


def test_pending_renderable_shows_elapsed_seconds(monkeypatch):
    """Elapsed seconds should be visibly formatted, e.g. '5.0s' or '0:00:05'."""
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    import parliament.render.cli_live as mod
    monkeypatch.setattr(mod.time, "monotonic", fake_monotonic)

    r = RichLiveRenderer(console=Console(file=io.StringIO(), force_terminal=False))
    r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))

    # Advance virtual time by 7.3 seconds
    fake_now[0] = 1007.3
    text = _render_to_text(r._render_pending())
    # Accept any of common formats: "7.3s" / "0:00:07" / "00:07"
    assert (
        "7.3s" in text or "0:00:07" in text or "00:07" in text
    ), f"elapsed not visible in: {text!r}"


def test_completed_event_still_prints_response_panel(recording_console):
    """Regression: the per-response panel must still appear in scrollback after spinner work."""
    console, _ = recording_console
    r = RichLiveRenderer(console=console)
    response = Response(
        member_name="Alpha",
        content="The case for Postgres is strong.",
        phase="first_reading",
        duration_ms=2300,
    )
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Alpha",
                kind="completed",
                response=response,
                duration_ms=2300,
            )
        )
    output = recording_console[1].getvalue()
    assert "Alpha" in output
    assert "case for Postgres" in output


def test_completed_event_can_hide_response_panel(recording_console):
    """No-show-debate mode keeps status events but omits intermediate response panels."""
    console, _ = recording_console
    r = RichLiveRenderer(console=console, show_responses=False)
    response = Response(
        member_name="Alpha",
        content="This intermediate answer should stay hidden.",
        phase="first_reading",
        duration_ms=2300,
    )
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Alpha",
                kind="completed",
                response=response,
                duration_ms=2300,
            )
        )
    output = recording_console[1].getvalue()
    assert "First Reading" in output
    assert "This intermediate answer should stay hidden." not in output


# ---------- TTY-aware lifecycle ----------


def test_live_is_skipped_on_non_terminal_console(recording_console):
    """When stdout isn't a TTY (pipe, file, test capture), don't try to animate."""
    console, _ = recording_console
    assert console.is_terminal is False
    r = RichLiveRenderer(console=console)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        # No exception, no Live started.
        assert r._live is None


def test_live_is_started_on_terminal_console():
    """On a real TTY, Rich Live is engaged so the spinner can animate."""
    # Force a terminal context with a recording-friendly buffer.
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    r = RichLiveRenderer(console=console)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        assert r._live is not None
    # After exit, Live is torn down.
    assert r._live is None
