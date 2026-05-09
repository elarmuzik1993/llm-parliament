"""Renderer protocol — context-manager lifecycle and live status behavior."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from parliament.core.types import ProgressEvent, Response, Synthesis
from parliament.render import (
    DebateRenderer,
    RichLiveRenderer,
    SilentRenderer,
    build_renderer,
)


# ---------- SilentRenderer ----------


def test_silent_renderer_is_a_debate_renderer():
    r = SilentRenderer()
    assert isinstance(r, DebateRenderer)


def test_silent_renderer_is_a_context_manager():
    r = SilentRenderer()
    with r as inner:
        assert inner is r


def test_silent_renderer_emit_produces_nothing():
    """SilentRenderer.emit must be safe to call and produce no observable side effect."""
    r = SilentRenderer()
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="A", kind="started"))
        r.emit(ProgressEvent(phase="first_reading", member_name="A", kind="completed",
                             response=Response(member_name="A", content="x", phase="first_reading")))
    # No assertion needed — test passes if nothing raised


# ---------- build_renderer factory ----------


def test_build_renderer_returns_rich_status_when_off():
    r = build_renderer(show_debate=False, mode="cli", console=Console())
    assert isinstance(r, RichLiveRenderer)
    assert r._show_responses is False


def test_build_renderer_returns_rich_for_cli_when_on():
    r = build_renderer(show_debate=True, mode="cli", console=Console())
    assert isinstance(r, RichLiveRenderer)


def test_build_renderer_unknown_mode_raises():
    with pytest.raises(ValueError, match="mode"):
        build_renderer(show_debate=True, mode="hologram", console=Console())


# ---------- RichLiveRenderer ----------


@pytest.fixture
def recording_console():
    """A Rich Console that captures output as a string."""
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120, record=True), buf


def _drain(console_buf: tuple[Console, io.StringIO]) -> str:
    """Return all output written to the console."""
    return console_buf[1].getvalue()


def test_rich_renderer_prints_first_reading_header(recording_console):
    console, _ = recording_console
    r = RichLiveRenderer(console=console)
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
    output = _drain(recording_console)
    # Stage header should appear as the first phase begins.
    assert "First Reading" in output


def test_rich_renderer_renders_response_content_on_completed(recording_console):
    console, _ = recording_console
    r = RichLiveRenderer(console=console)
    response = Response(
        member_name="Alpha",
        content="The case for Postgres is strong.",
        phase="first_reading",
        duration_ms=1200,
    )
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="Alpha", kind="started"))
        r.emit(
            ProgressEvent(
                phase="first_reading",
                member_name="Alpha",
                kind="completed",
                response=response,
                duration_ms=1200,
            )
        )
    output = _drain(recording_console)
    assert "Alpha" in output
    assert "case for Postgres" in output


def test_rich_renderer_shows_each_phase_header(recording_console):
    console, _ = recording_console
    r = RichLiveRenderer(console=console)
    response_fr = Response(member_name="A", content="fr-content", phase="first_reading")
    response_dbt = Response(member_name="A", content="debate-content", phase="debate")
    synth = Synthesis(speaker_name="A", recommendation="ship it")
    with r:
        r.emit(ProgressEvent(phase="first_reading", member_name="A", kind="started"))
        r.emit(ProgressEvent(phase="first_reading", member_name="A", kind="completed",
                             response=response_fr, duration_ms=10))
        r.emit(ProgressEvent(phase="debate", member_name="A", kind="started"))
        r.emit(ProgressEvent(phase="debate", member_name="A", kind="completed",
                             response=response_dbt, duration_ms=10))
        r.emit(ProgressEvent(phase="division", member_name="A", kind="started"))
        r.emit(ProgressEvent(phase="division", member_name="A", kind="completed",
                             synthesis=synth, duration_ms=10))
    output = _drain(recording_console)
    assert "First Reading" in output
    assert "Debate" in output
    assert "Division" in output


def test_rich_renderer_shows_failure_with_error(recording_console):
    console, _ = recording_console
    r = RichLiveRenderer(console=console)
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
    output = _drain(recording_console)
    assert "Beta" in output
    # Error text should surface visibly, not be silently swallowed.
    assert "synthetic failure" in output.lower() or "failed" in output.lower()
