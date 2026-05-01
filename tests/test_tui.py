"""TUI state-building and persistence tests."""

import json

from parliament.core.types import Bill, Hansard, Member, Response, Synthesis
from parliament.tui import (
    AppSettings,
    build_model_settings,
    load_app_settings,
    save_app_settings,
    save_hansard,
)


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


def test_app_settings_round_trip(monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("parliament.tui.SETTINGS_FILE", settings_file)

    save_app_settings(AppSettings(save_dir=str(tmp_path / "hansards")))

    loaded = load_app_settings()
    assert loaded.save_dir == str(tmp_path / "hansards")
    assert json.loads(settings_file.read_text()) == {"save_dir": str(tmp_path / "hansards")}


def test_save_hansard_writes_markdown(monkeypatch, tmp_path):
    hansard = Hansard(
        bill=Bill(content="Should we use PostgreSQL?"),
        members=[
            Member(name="A", provider_name="mock", model="mock-v1", tier=3),
            Member(name="B", provider_name="mock", model="mock-v2", tier=3),
        ],
        first_reading=[Response(member_name="A", content="yes", phase="first_reading")],
        debate=[Response(member_name="B", content="agree", phase="debate")],
        synthesis=Synthesis(
            speaker_name="A",
            consensus="Use PostgreSQL.",
            recommendation="Proceed.",
        ),
    )

    path = save_hansard(hansard, str(tmp_path / "responses"))

    assert path.parent == tmp_path / "responses"
    assert path.suffix == ".md"
    assert path.exists()
    content = path.read_text()
    assert "type: parliament-hansard" in content
    assert "# Should we use PostgreSQL?" in content
    assert "## Question" in content
    assert "Should we use PostgreSQL?" in content
    assert "### Recommendation" in content
    assert "Proceed." in content
    assert "## First Reading" in content
    assert "## Debate" in content
