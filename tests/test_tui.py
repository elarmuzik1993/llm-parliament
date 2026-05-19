"""TUI state-building and persistence tests."""

import curses
import json

import yaml

from parliament import tui as tui_mod
from parliament.tui import (
    AppSettings,
    MemberEditorState,
    build_model_settings,
    load_app_settings,
    _mask_api_key,
    _model_picker_options,
    _draw_result,
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


def test_save_hansard_at_verdict_level_has_all_synthesis_sections(make_hansard, tmp_path):
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.VERDICT)

    text = path.read_text(encoding="utf-8")
    assert "# Should we use Postgres or MongoDB?" in text
    assert "> [!info] Consensus" in text
    assert "> [!warning] Split" in text
    assert "> [!danger] Risks" in text
    assert "> [!success] Recommendation" in text
    assert not text.startswith("---")
    assert "## First Reading" not in text


def test_save_hansard_default_level_is_archive(make_hansard, tmp_path):
    """Default save level is ARCHIVE — full synthesis + frontmatter, no transcripts."""
    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path))

    text = path.read_text(encoding="utf-8")
    assert "> [!info] Consensus" in text
    assert "> [!success] Recommendation" in text
    assert text.startswith("---")       # frontmatter present
    assert "## First Reading" not in text  # transcripts excluded


def test_save_hansard_writes_full_level_with_transcripts(make_hansard, tmp_path):
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.FULL)

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")  # frontmatter
    assert "## First Reading" in text
    assert "## Debate" in text
    assert "## Session" in text


def test_save_hansard_filename_includes_slug_and_id_prefix(make_hansard, tmp_path):
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.VERDICT)

    name = path.name
    # Format: YYYYMMDD-HHMMSS-slug-shortid.md
    assert name.endswith(".md")
    assert hansard.id[:8] in name


class _FakeStdscr:
    def __init__(self, height=24, width=100):
        self._h = height
        self._w = width
        self.lines: list[tuple[int, int, str, int]] = []

    def getmaxyx(self):
        return (self._h, self._w)

    def addnstr(self, y, x, text, n, attr=0):
        self.lines.append((y, x, text[:n], attr))

    def addstr(self, y, x, text, attr=0):
        self.lines.append((y, x, text, attr))

    def attr_for(self, text: str) -> int:
        return next(attr for _, _, value, attr in self.lines if value == text)


def test_result_screen_uses_colored_verdict_sections(make_hansard, monkeypatch):
    monkeypatch.setattr(tui_mod, "_TUI_COLORS_READY", True)
    monkeypatch.setattr(tui_mod.curses, "color_pair", lambda pair: pair << 8)

    scr = _FakeStdscr()
    _draw_result(scr, make_hansard(), top=0, height=24, width=100, message="", save_dir=None)

    assert scr.attr_for("Verdict") & curses.A_BOLD
    assert scr.attr_for("CONSENSUS") != scr.attr_for("SPLIT")
    assert scr.attr_for("SPLIT") != scr.attr_for("RISKS")
    assert scr.attr_for("RISKS") != scr.attr_for("RECOMMENDATION")
    assert scr.attr_for("RECOMMENDATION") & curses.A_BOLD


# ---------- TUI result screen respects hansard level ----------


def test_result_screen_minimal_level_shows_only_recommendation(make_hansard):
    """At hansard.level=minimal, the TUI result screen must hide Consensus / Split / Risks."""
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _result_lines

    lines = _result_lines(make_hansard(), HansardLevel.MINIMAL)
    body = "\n".join(lines)

    assert "RECOMMENDATION" in body
    assert "CONSENSUS" not in body
    assert "SPLIT" not in body
    assert "RISKS" not in body


def test_result_screen_verdict_level_shows_all_four_sections(make_hansard):
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _result_lines

    body = "\n".join(_result_lines(make_hansard(), HansardLevel.VERDICT))

    assert "CONSENSUS" in body
    assert "SPLIT" in body
    assert "RISKS" in body
    assert "RECOMMENDATION" in body


def test_result_screen_minimal_level_hides_session_footer(make_hansard):
    """The Session/Calls/Speaker/Hansard footer is metadata; gated by archive+ levels."""
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _result_lines

    body = "\n".join(_result_lines(make_hansard(), HansardLevel.MINIMAL))
    assert "Session:" not in body
    assert "Calls:" not in body


def test_result_screen_archive_level_shows_session_footer(make_hansard):
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _result_lines

    body = "\n".join(_result_lines(make_hansard(), HansardLevel.ARCHIVE))
    assert "Session:" in body
    assert "Calls:" in body
    assert "Speaker:" in body


def test_draw_result_threads_level_through(make_hansard, monkeypatch):
    monkeypatch.setattr(tui_mod, "_TUI_COLORS_READY", True)
    monkeypatch.setattr(tui_mod.curses, "color_pair", lambda pair: pair << 8)

    from parliament.render.hansard import HansardLevel

    scr = _FakeStdscr()
    _draw_result(
        scr,
        make_hansard(),
        top=0,
        height=24,
        width=100,
        message="",
        save_dir=None,
        level=HansardLevel.MINIMAL,
    )
    body = "\n".join(line for _, _, line, _ in scr.lines)
    assert "RECOMMENDATION" in body
    assert "CONSENSUS" not in body


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
