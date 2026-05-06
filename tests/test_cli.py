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
    # Verdict still prints at the end.
    assert "VERDICT" in result.output
    # Mock provider's content should appear in the live panels.
    assert "Mock" in result.output


def test_ask_no_show_debate_suppresses_live_view(monkeypatch):
    """--no-show-debate hides intermediate panels; only the verdict prints."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "Test?"]
    )

    assert result.exit_code == 0, result.output
    # Live phase headers should NOT appear.
    # The "Parliament Session" and "VERDICT" rules still print, but the
    # specific live phase markers are absent.
    assert _LIVE_FIRST_READING_MARKER not in result.output
    assert _LIVE_DEBATE_MARKER not in result.output
    # Note: "Division" is also absent because the live renderer is silent.
    assert "VERDICT" in result.output


def test_ask_env_var_disables_live_view(monkeypatch):
    """PARLIAMENT_SHOW_DEBATE=0 in the env suppresses the live view when no flag is set."""
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")

    result = CliRunner().invoke(cli.main, ["ask", "--mock", "Test?"])

    assert result.exit_code == 0, result.output
    assert _LIVE_FIRST_READING_MARKER not in result.output
    assert "VERDICT" in result.output


def test_ask_cli_flag_overrides_env(monkeypatch):
    """--show-debate beats PARLIAMENT_SHOW_DEBATE=0."""
    monkeypatch.setenv("PARLIAMENT_SHOW_DEBATE", "0")

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--show-debate", "Test?"]
    )

    assert result.exit_code == 0, result.output
    assert _LIVE_FIRST_READING_MARKER in result.output


def test_ask_verbose_coexists_with_show_debate(monkeypatch):
    """--verbose still prints the post-hoc dump; --show-debate adds the live view too."""
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--verbose", "Test?"]
    )

    assert result.exit_code == 0, result.output
    # Both the live view and the verbose post-hoc rules render.
    assert _LIVE_FIRST_READING_MARKER in result.output
    # The post-hoc verbose dump also draws "FIRST READING" rules — confirm we
    # got at least two First Reading occurrences (one live, one verbose).
    assert result.output.count("FIRST READING") + result.output.count(
        "First Reading"
    ) >= 2
