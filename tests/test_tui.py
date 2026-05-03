"""TUI state-building and persistence tests."""

import json

import yaml

from parliament.core.types import Bill, Hansard, Member, Response, Synthesis
from parliament.tui import (
    AppSettings,
    MemberEditorState,
    build_model_settings,
    load_app_settings,
    _mask_api_key,
    _model_picker_options,
    _save_member_edit,
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


def test_member_edit_updates_active_config(tmp_path):
    config = {
        "parliament": {
            "name": "House of AI",
            "members": [
                {"name": "Llama", "provider": "ollama", "model": "llama3.1"},
                {"name": "Gemma", "provider": "ollama", "model": "gemma2"},
            ],
        },
        "providers": {
            "ollama": {"base_url": "http://localhost:11434/v1"},
        },
    }
    config_path = tmp_path / "config.yaml"

    editor = MemberEditorState(
        member_index=0,
        draft={
            "name": "Llama",
            "provider": "ollama",
            "model": "mistral",
            "base_url": "http://localhost:11435/v1",
        },
    )

    updated = _save_member_edit(config, config_path, editor)

    loaded = yaml.safe_load(config_path.read_text())
    assert loaded["parliament"]["members"][0]["model"] == "mistral"
    assert loaded["providers"]["ollama"]["base_url"] == "http://localhost:11435/v1"
    assert updated["parliament"]["members"][0]["model"] == "mistral"


def test_member_edit_preserves_placeholder_secrets(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
parliament:
  name: House of AI
  members:
    - name: Claude
      provider: anthropic
      model: claude-sonnet-4-6
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
""".strip()
        + "\n"
    )
    runtime_config = {
        "parliament": {
            "name": "House of AI",
            "members": [
                {"name": "Claude", "provider": "anthropic", "model": "claude-sonnet-4-6"},
            ],
        },
        "providers": {
            "anthropic": {"api_key": "sk-ant-real-secret"},
        },
    }
    editor = MemberEditorState(
        member_index=0,
        draft={
            "name": "Claude",
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "base_url": "",
        },
    )

    _save_member_edit(runtime_config, config_path, editor)

    saved = config_path.read_text()
    assert "${ANTHROPIC_API_KEY}" in saved
    assert "sk-ant-real-secret" not in saved


def test_model_picker_options_include_custom(monkeypatch):
    from parliament import tui as tui_module
    from parliament.model_catalog import PickerData

    monkeypatch.setattr(
        tui_module,
        "picker_data_for",
        lambda provider, config=None: PickerData(models=["llama3.1"], notice=None),
    )

    options, notice = _model_picker_options("ollama")

    assert options[-1] == "__custom__"
    assert "llama3.1" in options
    assert notice is None


def test_model_picker_options_propagates_notice(monkeypatch):
    from parliament import tui as tui_module
    from parliament.model_catalog import PickerData

    monkeypatch.setattr(
        tui_module,
        "picker_data_for",
        lambda provider, config=None: PickerData(
            models=[],
            notice="No API key for openai. Set one with: parliament keys set openai <key>",
        ),
    )

    options, notice = _model_picker_options("openai")

    assert options == ["__custom__"]
    assert notice is not None
    assert "No API key" in notice


def test_member_save_autonames_from_model(tmp_path):
    config = {
        "parliament": {
            "name": "House of AI",
            "members": [
                {"name": "Llama", "provider": "ollama", "model": "llama3.1"},
                {"name": "Gemma", "provider": "ollama", "model": "gemma2"},
            ],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    config_path = tmp_path / "config.yaml"
    editor = MemberEditorState(
        member_index=0,
        draft={
            "name": "Llama",
            "provider": "ollama",
            "model": "mistral",
            "base_url": "",
        },
    )

    updated = _save_member_edit(config, config_path, editor)

    assert updated["parliament"]["members"][0]["name"] == "mistral"
    assert updated["parliament"]["members"][1]["name"] == "gemma2"
    saved = yaml.safe_load(config_path.read_text())
    assert saved["parliament"]["members"][0]["name"] == "mistral"


def test_member_save_disambiguates_duplicate_models(tmp_path):
    config = {
        "parliament": {
            "name": "House of AI",
            "members": [
                {"name": "First", "provider": "ollama", "model": "llama3:latest"},
                {"name": "Second", "provider": "ollama", "model": "gemma2"},
                {"name": "Third", "provider": "ollama", "model": "mistral"},
            ],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    config_path = tmp_path / "config.yaml"
    editor = MemberEditorState(
        member_index=1,
        draft={
            "name": "Second",
            "provider": "ollama",
            "model": "llama3:latest",
            "base_url": "",
        },
    )

    updated = _save_member_edit(config, config_path, editor)

    names = [m["name"] for m in updated["parliament"]["members"]]
    assert names == ["llama3:latest", "llama3:latest #2", "mistral"]


def test_mask_api_key_short_keys_fully_masked():
    assert _mask_api_key("") == ""
    assert _mask_api_key("abcd") == "••••"
    assert _mask_api_key("abc") == "•••"


def test_mask_api_key_shows_last_four():
    assert _mask_api_key("sk-ant-123456abcd") == "•" * 13 + "abcd"


def test_member_save_updates_editor_draft_name(tmp_path):
    config = {
        "parliament": {
            "name": "House of AI",
            "members": [
                {"name": "OldName", "provider": "ollama", "model": "llama3.1"},
            ],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    config_path = tmp_path / "config.yaml"
    editor = MemberEditorState(
        member_index=0,
        draft={
            "name": "OldName",
            "provider": "ollama",
            "model": "gemma2",
            "base_url": "",
        },
    )

    _save_member_edit(config, config_path, editor)

    assert editor.draft["name"] == "gemma2"
