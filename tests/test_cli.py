"""CLI behavior tests."""

from click.testing import CliRunner

from parliament import cli


def test_bare_command_launches_tui(monkeypatch):
    calls = {}

    monkeypatch.setattr(cli, "load_config", lambda config_path=None: {"loaded": True})

    def fake_build_model_settings(config, speaker_override=None):
        calls["config"] = config
        calls["speaker"] = speaker_override
        return ["settings"]

    def fake_run_tui(settings):
        calls["settings"] = settings

    import parliament.tui

    monkeypatch.setattr(parliament.tui, "build_model_settings", fake_build_model_settings)
    monkeypatch.setattr(parliament.tui, "run_tui", fake_run_tui)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0
    assert calls == {
        "config": {"loaded": True},
        "speaker": None,
        "settings": ["settings"],
    }


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
