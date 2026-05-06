"""TUI live-debate wiring — show_debate config flows into the renderer choice."""

from __future__ import annotations

from typing import Any

import pytest

from parliament import tui as tui_mod
from parliament.core.types import Hansard, Bill, Synthesis
from parliament.render import CursesLiveRenderer, SilentRenderer


class _FakeStdscr:
    def getmaxyx(self) -> tuple[int, int]:
        return (24, 80)

    def erase(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def addnstr(self, *args, **kwargs) -> None:  # noqa: D401, ARG002
        pass

    def addstr(self, *args, **kwargs) -> None:  # noqa: D401, ARG002
        pass


@pytest.fixture
def fake_run(monkeypatch):
    """Replace Parliament.ask with a stub returning a minimal Hansard, and capture inputs."""
    captured: dict[str, Any] = {}

    class _StubParliament:
        def __init__(self, members, providers, on_progress=None, speaker_override=None):
            captured["on_progress"] = on_progress
            captured["members"] = members

        def check_gaps(self):  # pragma: no cover - not exercised here
            return []

        async def ask(self, question, last_speaker=None):
            captured["question"] = question
            return Hansard(
                bill=Bill(content=question),
                members=captured["members"],
                first_reading=[],
                debate=[],
                synthesis=Synthesis(speaker_name="Mock-A"),
            )

    monkeypatch.setattr(tui_mod, "Parliament", _StubParliament)
    return captured


def _mock_config():
    return {
        "parliament": {
            "name": "Mock",
            "members": [
                {"name": "Mock-A", "provider": "mock", "model": "mock-v1"},
                {"name": "Mock-B", "provider": "mock", "model": "mock-v2"},
            ],
        },
        "providers": {},
    }


def test_run_debate_uses_curses_renderer_when_show_debate_on(monkeypatch, fake_run):
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    captured_renderers: list[Any] = []
    real_build = tui_mod.build_renderer

    def spy_build(*, show_debate, mode, console=None, stdscr=None):
        r = real_build(show_debate=show_debate, mode=mode, console=console, stdscr=stdscr)
        captured_renderers.append((show_debate, mode, r))
        return r

    monkeypatch.setattr(tui_mod, "build_renderer", spy_build)

    config = _mock_config()  # no display section -> default ON
    tui_mod._run_debate(_FakeStdscr(), "Test?", config, speaker_override=None)

    assert captured_renderers, "build_renderer should be called from _run_debate"
    show_debate, mode, renderer = captured_renderers[-1]
    assert show_debate is True
    assert mode == "tui"
    assert isinstance(renderer, CursesLiveRenderer)
    # The renderer's emit was wired into Parliament.
    assert fake_run["on_progress"] == renderer.emit


def test_run_debate_uses_silent_renderer_when_show_debate_off(monkeypatch, fake_run):
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    captured_renderers: list[Any] = []
    real_build = tui_mod.build_renderer

    def spy_build(*, show_debate, mode, console=None, stdscr=None):
        r = real_build(show_debate=show_debate, mode=mode, console=console, stdscr=stdscr)
        captured_renderers.append((show_debate, mode, r))
        return r

    monkeypatch.setattr(tui_mod, "build_renderer", spy_build)

    config = _mock_config()
    config["display"] = {"show_debate": False}

    tui_mod._run_debate(_FakeStdscr(), "Test?", config, speaker_override=None)

    show_debate, mode, renderer = captured_renderers[-1]
    assert show_debate is False
    assert isinstance(renderer, SilentRenderer)


def test_run_debate_env_var_disables_live_view(monkeypatch, fake_run):
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")

    captured_renderers: list[Any] = []
    real_build = tui_mod.build_renderer

    def spy_build(*, show_debate, mode, console=None, stdscr=None):
        r = real_build(show_debate=show_debate, mode=mode, console=console, stdscr=stdscr)
        captured_renderers.append((show_debate, mode, r))
        return r

    monkeypatch.setattr(tui_mod, "build_renderer", spy_build)

    config = _mock_config()  # display absent -> env wins
    tui_mod._run_debate(_FakeStdscr(), "Test?", config, speaker_override=None)

    show_debate, _, renderer = captured_renderers[-1]
    assert show_debate is False
    assert isinstance(renderer, SilentRenderer)
