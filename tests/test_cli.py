"""CLI behavior tests."""

from click.testing import CliRunner

from parliament import cli


# Sentinel strings the live renderer prints on each phase header.
_LIVE_FIRST_READING_MARKER = "First Reading"
_LIVE_DEBATE_MARKER = "Debate"
_LIVE_DIVISION_MARKER = "Division"


def test_bare_command_launches_tui(monkeypatch):
    calls = {}

    monkeypatch.setattr(cli, "load_config", lambda config_path=None: {"loaded": True})

    def fake_build_model_settings(config, speaker_override=None):
        calls["config"] = config
        calls["speaker"] = speaker_override
        return ["settings"]

    def fake_run_tui(settings, config, config_path, speaker_override=None, mock=False):
        calls["settings"] = settings
        calls["run_config"] = config
        calls["run_config_path"] = config_path
        calls["run_speaker"] = speaker_override
        calls["run_mock"] = mock

    import parliament.tui

    monkeypatch.setattr(parliament.tui, "build_model_settings", fake_build_model_settings)
    monkeypatch.setattr(parliament.tui, "run_tui", fake_run_tui)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0
    assert calls == {
        "config": {"loaded": True},
        "speaker": None,
        "settings": ["settings"],
        "run_config": {"loaded": True},
        "run_config_path": None,
        "run_speaker": None,
        "run_mock": False,
    }


def test_mock_config_uses_mock_members():
    config = cli._mock_config()

    members = config["parliament"]["members"]
    assert [member["provider"] for member in members] == ["mock", "mock", "mock"]
    assert [member["name"] for member in members] == ["Mock-A", "Mock-B", "Mock-C"]


def test_keys_list_empty_shows_keys_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "KEYS_FILE", tmp_path / "keys.env")
    monkeypatch.setattr(cli, "load_keys", lambda: {})
    for env_var in cli.KEY_PROVIDERS.values():
        monkeypatch.delenv(env_var, raising=False)

    result = CliRunner().invoke(cli.main, ["keys", "list"])

    assert result.exit_code == 0
    assert "No API keys configured" in result.output
    assert str(tmp_path / "keys.env") in result.output
    assert "{KEYS_FILE}" not in result.output


def test_keys_list_masks_file_keys(monkeypatch):
    secret = "sk-test-secret-123456"
    monkeypatch.setattr(cli, "load_keys", lambda: {"OPENAI_API_KEY": secret})
    for env_var in cli.KEY_PROVIDERS.values():
        monkeypatch.delenv(env_var, raising=False)

    result = CliRunner().invoke(cli.main, ["keys", "list"])

    assert result.exit_code == 0
    assert "API Keys" in result.output
    assert "openai" in result.output
    assert "OPENAI_API_KEY" in result.output
    assert "sk-tes****3456" in result.output
    assert secret not in result.output


def test_keys_list_includes_environment_keys(monkeypatch):
    secret = "sk-ant-env-abcdef"
    monkeypatch.setattr(cli, "load_keys", lambda: {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = CliRunner().invoke(cli.main, ["keys", "list"])

    assert result.exit_code == 0
    assert "anthropic" in result.output
    assert "environment" in result.output
    assert "sk-ant****cdef" in result.output
    assert secret not in result.output


# ---------- ask --show-debate / --no-show-debate ----------


def test_ask_default_shows_live_debate(monkeypatch):
    """Default behavior (no flag, no env, no config) renders live phase headers."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(cli.main, ["ask", "--mock", "Postgres or Mongo?"])

    assert result.exit_code == 0, result.output
    # All three phase headers should appear before the final verdict.
    assert _LIVE_FIRST_READING_MARKER in result.output
    assert _LIVE_DEBATE_MARKER in result.output
    assert _LIVE_DIVISION_MARKER in result.output
    # Post-run verdict panel prints at the end.
    assert "Parliament Verdict" in result.output
    # Mock provider's content should appear in the live panels.
    assert "Mock" in result.output


def test_ask_no_show_debate_keeps_live_status(monkeypatch):
    """--no-show-debate hides response panels but keeps live phase/status feedback."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "Test?"]
    )

    assert result.exit_code == 0, result.output
    assert _LIVE_FIRST_READING_MARKER in result.output
    assert _LIVE_DEBATE_MARKER in result.output
    assert "Parliament Verdict" in result.output


def test_ask_env_var_hides_response_panels_but_keeps_status(monkeypatch):
    """PARLIAMENT_SHOW_DEBATE=0 hides responses but keeps live status when no flag is set."""
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")

    result = CliRunner().invoke(cli.main, ["ask", "--mock", "Test?"])

    assert result.exit_code == 0, result.output
    assert _LIVE_FIRST_READING_MARKER in result.output
    assert "Parliament Verdict" in result.output


def test_ask_cli_flag_overrides_env(monkeypatch):
    """--show-debate beats PARLIAMENT_SHOW_DEBATE=0."""
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--show-debate", "Test?"]
    )

    assert result.exit_code == 0, result.output
    assert _LIVE_FIRST_READING_MARKER in result.output


def test_ask_verbose_coexists_with_show_debate(monkeypatch):
    """--verbose aliases to --hansard=full; live view + full post-run output."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--verbose", "Test?"]
    )

    assert result.exit_code == 0, result.output
    # Live view renders "First Reading"; full-level post-run also emits "📖 First Reading"
    assert result.output.count("First Reading") >= 2


# ── New hansard-level tests ──────────────────────────────────────────────────

_VERDICT_RECOMMENDATION_MARKER = "✓ Recommendation"
_FULL_TRANSCRIPT_MARKER = "📖 First Reading"


def test_ask_default_uses_verdict_level(monkeypatch):
    """Default behavior: post-run terminal shows verdict block, no transcripts."""
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(cli.main, ["ask", "--mock", "--no-show-debate", "Test?"])

    assert result.exit_code == 0, result.output
    # All four verdict panels appear; no transcripts.
    assert "ℹ Consensus" in result.output
    assert "⚖ Split" in result.output
    assert "! Risks" in result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert _FULL_TRANSCRIPT_MARKER not in result.output


def test_ask_minimal_level_omits_other_verdict_sections(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--hansard", "minimal", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert "ℹ Consensus" not in result.output
    assert "⚖ Split" not in result.output


def test_ask_full_level_shows_transcripts(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--hansard", "full", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _FULL_TRANSCRIPT_MARKER in result.output
    assert "🗣 Debate" in result.output


def test_verbose_flag_aliases_to_full(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--verbose", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _FULL_TRANSCRIPT_MARKER in result.output


def test_explicit_hansard_flag_wins_over_verbose(monkeypatch):
    """When both --verbose and --hansard are passed, --hansard wins (more specific)."""
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main,
        ["ask", "--mock", "--no-show-debate", "--verbose", "--hansard", "verdict", "Test?"],
    )
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert _FULL_TRANSCRIPT_MARKER not in result.output


def test_env_var_sets_level(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "minimal")
    result = CliRunner().invoke(cli.main, ["ask", "--mock", "--no-show-debate", "Test?"])
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert "ℹ Consensus" not in result.output


# ---------- parliament update CLI subcommand ----------


def test_update_cli_success_exits_zero(monkeypatch):
    """`parliament update` happy path: editable install + git pull succeeds → exit 0."""
    import parliament.commands as cmd_mod

    monkeypatch.setattr(
        cmd_mod, "_detect_install", lambda: ("editable", __import__("pathlib").Path("/tmp/fake-repo")),
    )
    import subprocess as sp

    def fake_run(cmd, **kwargs):
        return sp.CompletedProcess(args=cmd, returncode=0, stdout="Already up to date.\n", stderr="")

    monkeypatch.setattr("parliament.commands.subprocess.run", fake_run)

    result = CliRunner().invoke(cli.main, ["update"])
    assert result.exit_code == 0, result.output
    assert "Updated" in result.output or "Restart" in result.output


def test_update_cli_non_editable_install_exits_one(monkeypatch):
    """Pipx/pip installs aren't supported yet → exit 1 with explanation."""
    import parliament.commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "_detect_install", lambda: ("non-editable", None))

    result = CliRunner().invoke(cli.main, ["update"])
    assert result.exit_code == 1
    assert "editable" in result.output.lower() or "pipx" in result.output.lower()


def test_update_cli_pull_failure_exits_one(monkeypatch):
    import parliament.commands as cmd_mod
    from pathlib import Path

    monkeypatch.setattr(cmd_mod, "_detect_install", lambda: ("editable", Path("/tmp/fake")))

    import subprocess as sp

    def fake_run(cmd, **kwargs):
        return sp.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="fatal: conflict\n")

    monkeypatch.setattr("parliament.commands.subprocess.run", fake_run)

    result = CliRunner().invoke(cli.main, ["update"])
    assert result.exit_code == 1
    assert "fail" in result.output.lower() or "conflict" in result.output.lower()
