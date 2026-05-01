"""TUI state-building tests."""

from parliament.tui import build_model_settings


def test_build_model_settings_roles_and_key_status(monkeypatch):
    monkeypatch.setattr("parliament.tui.load_keys", lambda: {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    settings = build_model_settings({
        "parliament": {
            "members": [
                {"name": "Claude", "provider": "anthropic", "model": "claude-sonnet-4-6"},
                {"name": "Llama", "provider": "ollama", "model": "llama3.1"},
                {"name": "GPT", "provider": "openai", "model": "gpt-4o"},
            ],
        },
        "providers": {
            "ollama": {"base_url": "http://localhost:11434/v1"},
        },
    })

    by_name = {setting.member.name: setting for setting in settings}
    assert by_name["GPT"].role == "Speaker / member"
    assert by_name["Claude"].role == "Member"
    assert by_name["Claude"].api_key_status == "configured"
    assert by_name["GPT"].api_key_status == "missing"
    assert by_name["Llama"].api_key_status == "not required"
    assert by_name["Llama"].base_url == "http://localhost:11434/v1"


def test_build_model_settings_speaker_override(monkeypatch):
    monkeypatch.setattr("parliament.tui.load_keys", lambda: {})

    settings = build_model_settings(
        {
            "parliament": {
                "members": [
                    {"name": "Claude", "provider": "anthropic", "model": "claude-sonnet-4-6"},
                    {"name": "Llama", "provider": "ollama", "model": "llama3.1"},
                ],
            },
        },
        speaker_override="Llama",
    )

    by_name = {setting.member.name: setting for setting in settings}
    assert by_name["Llama"].role == "Speaker / member"
    assert by_name["Claude"].role == "Member"
