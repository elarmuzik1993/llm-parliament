"""Tests for the slash-command registry and dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from parliament.commands import (
    COMMANDS,
    CommandContext,
    SpeakerOp,
    dispatch,
)
from parliament.core.types import Member


def _members() -> list[Member]:
    return [
        Member(name="Claude", provider_name="mock", model="mock-v1", tier=1),
        Member(name="Gemini", provider_name="mock", model="mock-v2", tier=2),
        Member(name="GPT", provider_name="mock", model="mock-v3", tier=2),
    ]


def _ctx(tmp_path: Path, **overrides) -> CommandContext:
    base = dict(
        members=_members(),
        speaker_override=None,
        hansard=None,
        save_dir=str(tmp_path),
    )
    base.update(overrides)
    return CommandContext(**base)


def test_unknown_command(tmp_path: Path) -> None:
    result = dispatch("/nope", _ctx(tmp_path))
    assert "Unknown command" in result.message
    assert result.clear_question is False


def test_help_lists_every_command(tmp_path: Path) -> None:
    result = dispatch("/help", _ctx(tmp_path))
    for cmd in COMMANDS:
        assert f"/{cmd.name}" in result.message


def test_help_alias_question_mark(tmp_path: Path) -> None:
    result = dispatch("/?", _ctx(tmp_path))
    assert "Available commands" in result.message


def test_help_is_case_insensitive(tmp_path: Path) -> None:
    result = dispatch("/HELP", _ctx(tmp_path))
    assert "Available commands" in result.message


def test_quit(tmp_path: Path) -> None:
    result = dispatch("/quit", _ctx(tmp_path))
    assert result.quit is True


def test_quit_alias_exit(tmp_path: Path) -> None:
    result = dispatch("/exit", _ctx(tmp_path))
    assert result.quit is True


def test_clear_clears_question(tmp_path: Path) -> None:
    result = dispatch("/clear", _ctx(tmp_path))
    assert result.clear_question is True
    assert result.message == ""


def test_reset(tmp_path: Path) -> None:
    result = dispatch("/reset", _ctx(tmp_path))
    assert result.clear_question is True
    assert result.speaker_op is SpeakerOp.CLEAR
    assert result.clear_hansard is True


def test_speaker_no_args_shows_current_default(tmp_path: Path) -> None:
    result = dispatch("/speaker", _ctx(tmp_path))
    assert "default" in result.message.lower()
    assert result.clear_question is False
    assert result.speaker_op is SpeakerOp.LEAVE


def test_speaker_no_args_shows_current_override(tmp_path: Path) -> None:
    result = dispatch("/speaker", _ctx(tmp_path, speaker_override="Claude"))
    assert "Claude" in result.message


def test_speaker_set_valid(tmp_path: Path) -> None:
    result = dispatch("/speaker Claude", _ctx(tmp_path))
    assert result.speaker_op is SpeakerOp.SET
    assert result.speaker_value == "Claude"


def test_speaker_set_case_insensitive(tmp_path: Path) -> None:
    result = dispatch("/speaker claude", _ctx(tmp_path))
    assert result.speaker_value == "Claude"


def test_speaker_set_invalid(tmp_path: Path) -> None:
    result = dispatch("/speaker NotAMember", _ctx(tmp_path))
    assert result.speaker_op is SpeakerOp.LEAVE
    assert "No member named" in result.message
    assert result.clear_question is False


def test_model_opens_picker(tmp_path: Path) -> None:
    result = dispatch("/model", _ctx(tmp_path))
    assert result.open_members_picker is True


def test_model_alias_members(tmp_path: Path) -> None:
    result = dispatch("/members", _ctx(tmp_path))
    assert result.open_members_picker is True


def test_settings_opens_screen(tmp_path: Path) -> None:
    result = dispatch("/settings", _ctx(tmp_path))
    assert result.open_screen == "app_settings"


def test_expand_toggles_panel(tmp_path: Path) -> None:
    result = dispatch("/expand", _ctx(tmp_path))
    assert result.toggle_members_panel is True


def test_collapse_alias_toggles_panel(tmp_path: Path) -> None:
    result = dispatch("/collapse", _ctx(tmp_path))
    assert result.toggle_members_panel is True


def test_history_empty_dir(tmp_path: Path) -> None:
    result = dispatch("/history", _ctx(tmp_path))
    assert "No saved verdicts" in result.message


def test_history_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = dispatch("/history", _ctx(tmp_path, save_dir=str(missing)))
    assert "No saved verdicts" in result.message


def test_history_lists_files(tmp_path: Path) -> None:
    (tmp_path / "20260101-x-aaaaaaaa.md").write_text("a")
    (tmp_path / "20260102-y-bbbbbbbb.md").write_text("b")
    result = dispatch("/history", _ctx(tmp_path))
    assert "Last 2 saved" in result.message
    assert "aaaaaaaa.md" in result.message
    assert "bbbbbbbb.md" in result.message


def test_history_respects_count_arg(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"2026010{i}-x-{i}{i}{i}{i}{i}{i}{i}{i}.md").write_text("x")
    result = dispatch("/history 2", _ctx(tmp_path))
    assert "Last 2 saved" in result.message


def test_history_invalid_count(tmp_path: Path) -> None:
    result = dispatch("/history abc", _ctx(tmp_path))
    assert "Invalid count" in result.message


def test_copy_without_hansard(tmp_path: Path) -> None:
    result = dispatch("/copy", _ctx(tmp_path))
    assert "No verdict" in result.message
    assert result.clear_question is False


def test_dispatch_rejects_non_command(tmp_path: Path) -> None:
    result = dispatch("just a question", _ctx(tmp_path))
    assert "Not a command" in result.message
    assert result.clear_question is False


def test_palette_matches_slash_only() -> None:
    from parliament.tui import _palette_matches

    matches = _palette_matches("/")
    assert [m.name for m in matches] == [c.name for c in COMMANDS]


def test_palette_matches_filters_by_prefix() -> None:
    from parliament.tui import _palette_matches

    names = [m.name for m in _palette_matches("/he")]
    assert "help" in names
    assert "quit" not in names


def test_palette_matches_empty_for_non_slash() -> None:
    from parliament.tui import _palette_matches

    assert _palette_matches("hello") == []


def test_palette_slash_only_lists_all() -> None:
    from parliament.tui import _command_palette_lines

    lines = _command_palette_lines("/")
    assert lines[0].startswith("Commands")
    for cmd in COMMANDS:
        assert any(f"/{cmd.name}" in line for line in lines[1:])


def test_palette_filters_by_prefix() -> None:
    from parliament.tui import _command_palette_lines

    lines = _command_palette_lines("/he")
    assert "matching '/he'" in lines[0]
    bodies = "\n".join(lines[1:])
    assert "/help" in bodies
    assert "/quit" not in bodies


def test_palette_no_match() -> None:
    from parliament.tui import _command_palette_lines

    lines = _command_palette_lines("/zzz")
    assert "No commands match" in lines[0]


def test_palette_matches_alias_prefix() -> None:
    from parliament.tui import _command_palette_lines

    lines = _command_palette_lines("/exi")
    bodies = "\n".join(lines[1:])
    assert "/quit" in bodies


def test_handler_exception_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from parliament import commands as cmd_mod

    def boom(_args, _ctx):
        raise RuntimeError("kaboom")

    original = cmd_mod.COMMANDS[:]
    cmd_mod.COMMANDS.append(cmd_mod.Command("boom", "test", boom))
    try:
        result = dispatch("/boom", _ctx(tmp_path))
        assert "Command failed" in result.message
        assert "kaboom" in result.message
    finally:
        cmd_mod.COMMANDS[:] = original
