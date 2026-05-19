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


def test_key_no_args_shows_usage(tmp_path: Path) -> None:
    result = dispatch("/key", _ctx(tmp_path))
    assert "Usage" in result.message
    assert result.open_key_input is None
    assert result.clear_question is False


def test_key_unknown_provider_rejected(tmp_path: Path) -> None:
    result = dispatch("/key ollama", _ctx(tmp_path))
    assert "Unknown provider" in result.message
    assert result.open_key_input is None
    assert result.clear_question is False


def test_key_valid_provider_opens_input(tmp_path: Path) -> None:
    for provider in ("anthropic", "openai", "google"):
        result = dispatch(f"/key {provider}", _ctx(tmp_path))
        assert result.open_key_input == provider
        assert result.message == ""


def test_key_provider_case_insensitive(tmp_path: Path) -> None:
    result = dispatch("/key OPENAI", _ctx(tmp_path))
    assert result.open_key_input == "openai"


def test_key_inline_secret_not_echoed(tmp_path: Path) -> None:
    """A user who accidentally types '/key openai sk-realsecret' must
    never see that secret echoed back in the dispatcher's message."""
    result = dispatch("/key openai sk-pretend-secret-9999", _ctx(tmp_path))
    assert result.open_key_input == "openai"
    assert "sk-pretend-secret-9999" not in result.message
    assert "command line" in result.message.lower()


def test_key_inline_secret_unknown_provider_not_echoed(tmp_path: Path) -> None:
    """Even when the provider token is wrong, only the first token is echoed —
    never the rest of the line, which may contain the key."""
    result = dispatch("/key foo sk-pretend-secret-9999", _ctx(tmp_path))
    assert "sk-pretend-secret-9999" not in result.message
    assert "Unknown provider 'foo'" in result.message


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


# ---------------- /update slash command ----------------


def test_update_command_registered() -> None:
    """/update appears in the registry with /upgrade as alias."""
    from parliament.commands import _resolve

    cmd = _resolve("update")
    assert cmd is not None
    assert cmd.name == "update"
    assert "upgrade" in cmd.aliases


def test_update_help_includes_summary(tmp_path: Path) -> None:
    """`/help` should list /update so users discover it."""
    result = dispatch("/help", _ctx(tmp_path))
    assert "/update" in result.message


# ---------------- _detect_install detection helper ----------------


def test_detect_install_editable_returns_path(tmp_path: Path, monkeypatch) -> None:
    """direct_url.json with editable=true and a file:// URL → editable + path."""
    from parliament import commands as cmd_mod

    fake_dist_info = tmp_path / "fake_dist-0.1.dist-info"
    fake_dist_info.mkdir()
    src_path = tmp_path / "src" / "parliament_pkg"
    src_path.mkdir(parents=True)
    direct_url = fake_dist_info / "direct_url.json"
    direct_url.write_text(
        '{"url": "' + tmp_path.as_uri() + '", "dir_info": {"editable": true}}',
        encoding="utf-8",
    )

    class _FakeDist:
        def read_text(self, name: str) -> str | None:
            if name == "direct_url.json":
                return direct_url.read_text(encoding="utf-8")
            return None

    monkeypatch.setattr(cmd_mod, "_dist_for_self", lambda: _FakeDist())

    kind, path = cmd_mod._detect_install()
    assert kind == "editable"
    assert path == tmp_path


def test_detect_install_non_editable_returns_kind_only(monkeypatch) -> None:
    """A non-editable direct_url (pipx/pip from PyPI) must NOT report editable."""
    from parliament import commands as cmd_mod

    class _FakeDist:
        def read_text(self, name: str) -> str | None:
            if name == "direct_url.json":
                return '{"url": "https://pypi.org/...", "archive_info": {}}'
            return None

    monkeypatch.setattr(cmd_mod, "_dist_for_self", lambda: _FakeDist())
    kind, path = cmd_mod._detect_install()
    assert kind != "editable"
    assert path is None


def test_detect_install_no_direct_url_file(monkeypatch) -> None:
    """Plain pip installs have no direct_url.json — must degrade gracefully."""
    from parliament import commands as cmd_mod

    class _FakeDist:
        def read_text(self, name: str) -> str | None:
            return None  # no direct_url.json

    monkeypatch.setattr(cmd_mod, "_dist_for_self", lambda: _FakeDist())
    kind, path = cmd_mod._detect_install()
    assert kind == "unknown"
    assert path is None


def test_detect_install_distribution_not_found(monkeypatch) -> None:
    """When the package metadata can't be located at all, we report 'unknown'."""
    from parliament import commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "_dist_for_self", lambda: None)
    kind, path = cmd_mod._detect_install()
    assert kind == "unknown"
    assert path is None


# ---------------- _update handler behavior ----------------


def _patch_install(monkeypatch, kind: str, path: Path | None) -> None:
    from parliament import commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "_detect_install", lambda: (kind, path))


def _patch_subprocess(monkeypatch, returncode: int = 0, stdout: str = "", stderr: str = "",
                      exception: Exception | None = None) -> list[list[str]]:
    """Replace subprocess.run with a recorder. Returns the call log."""
    import subprocess as sp

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if exception is not None:
            raise exception
        return sp.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("parliament.commands.subprocess.run", fake_run)
    return calls


def test_update_editable_success_quits(tmp_path: Path, monkeypatch) -> None:
    """Successful git pull → quit=True so the user re-launches."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_install(monkeypatch, "editable", repo)
    calls = _patch_subprocess(monkeypatch, returncode=0, stdout="Already up to date.\n")

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is True
    assert "Updated" in result.message or "Restart" in result.message
    # We should have invoked git pull --ff-only inside the repo
    assert any("git" in c[0] and "pull" in c for c in calls)
    assert any("--ff-only" in c for c in calls)


def test_update_editable_pull_failure_reports_error(tmp_path: Path, monkeypatch) -> None:
    """Non-zero git exit code → quit=False, error message echoed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_install(monkeypatch, "editable", repo)
    _patch_subprocess(
        monkeypatch,
        returncode=1,
        stderr="fatal: Not possible to fast-forward, aborting.\n",
    )

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is False
    assert "fast-forward" in result.message or "failed" in result.message.lower()


def test_update_pipx_success_quits(tmp_path: Path, monkeypatch) -> None:
    """pipx install → runs `pipx upgrade llm-parliament` and quits."""
    _patch_install(monkeypatch, "pipx", None)
    monkeypatch.setattr("parliament.commands.shutil.which", lambda _: "/usr/bin/pipx")
    calls = _patch_subprocess(monkeypatch, returncode=0, stdout="upgraded")

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is True
    assert "Restart" in result.message
    assert any("pipx" in c[0] and "upgrade" in c for c in calls)


def test_update_pipx_not_on_path(tmp_path: Path, monkeypatch) -> None:
    """pipx install but pipx binary missing → helpful message, no crash."""
    _patch_install(monkeypatch, "pipx", None)
    monkeypatch.setattr("parliament.commands.shutil.which", lambda _: None)

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is False
    assert "pipx" in result.message.lower()


def test_update_pip_user_success_quits(tmp_path: Path, monkeypatch) -> None:
    """pip user install → runs `pip install --upgrade llm-parliament` and quits."""
    _patch_install(monkeypatch, "pip-user", None)
    monkeypatch.setattr("parliament.commands.shutil.which", lambda _: "/usr/bin/pip")
    calls = _patch_subprocess(monkeypatch, returncode=0)

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is True
    assert any("pip" in c[0] and "--upgrade" in c for c in calls)


def test_update_pip_system_refuses(tmp_path: Path, monkeypatch) -> None:
    """System-wide pip install → refuse with a clear message, no subprocess."""
    _patch_install(monkeypatch, "pip-system", None)
    calls = _patch_subprocess(monkeypatch)

    result = dispatch("/update", _ctx(tmp_path))

    assert result.quit is False
    assert "sudo" in result.message.lower() or "system" in result.message.lower()
    assert calls == []


def test_update_unknown_install_explains(tmp_path: Path, monkeypatch) -> None:
    _patch_install(monkeypatch, "unknown", None)
    _patch_subprocess(monkeypatch)

    result = dispatch("/update", _ctx(tmp_path))
    assert result.quit is False
    assert result.message  # non-empty — user gets an explanation


def test_update_git_not_on_path(tmp_path: Path, monkeypatch) -> None:
    """If `git` isn't installed, surface a helpful message instead of crashing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_install(monkeypatch, "editable", repo)
    monkeypatch.setattr("parliament.commands.shutil.which", lambda _: None)

    result = dispatch("/update", _ctx(tmp_path))
    assert result.quit is False
    assert "git" in result.message.lower()


def test_update_subprocess_timeout(tmp_path: Path, monkeypatch) -> None:
    import subprocess as sp

    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_install(monkeypatch, "editable", repo)
    _patch_subprocess(monkeypatch, exception=sp.TimeoutExpired(cmd="git", timeout=60))

    result = dispatch("/update", _ctx(tmp_path))
    assert result.quit is False
    assert "tim" in result.message.lower()  # timeout / timed out


def test_update_alias_upgrade(tmp_path: Path, monkeypatch) -> None:
    """/upgrade should resolve to the same handler."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _patch_install(monkeypatch, "editable", repo)
    _patch_subprocess(monkeypatch, returncode=0)

    result = dispatch("/upgrade", _ctx(tmp_path))
    assert result.quit is True


# ---------------- /copy stale-import regression ----------------


def test_copy_uses_render_markdown_not_legacy_helper(tmp_path: Path, monkeypatch) -> None:
    """Regression: /copy used to import the deleted _hansard_markdown."""
    from parliament.core.types import Bill, Hansard, Member, Response, Synthesis

    hansard = Hansard(
        bill=Bill(content="Q?"),
        members=[Member(name="A", provider_name="mock", model="m", tier=3),
                 Member(name="B", provider_name="mock", model="m", tier=3)],
        first_reading=[Response(member_name="A", content="x", phase="first_reading")],
        debate=[Response(member_name="A", content="y", phase="debate")],
        synthesis=Synthesis(speaker_name="A", recommendation="ship it"),
        duration_ms=100,
    )
    captured: dict = {}

    def fake_clipboard(text: str) -> bool:
        captured["text"] = text
        return True

    import parliament.commands as cmd_mod
    monkeypatch.setattr(cmd_mod, "_copy_to_clipboard", fake_clipboard)

    ctx = _ctx(tmp_path, hansard=hansard)
    result = dispatch("/copy", ctx)

    assert "copied" in result.message.lower()
    # Sanity: the Hansard markdown body must include the recommendation
    assert "ship it" in captured["text"]
