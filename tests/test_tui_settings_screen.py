"""TUI settings screen — show_debate toggle persistence and key handling."""

from __future__ import annotations

import curses
from pathlib import Path

import yaml

from parliament import tui as tui_mod
from parliament.tui import (
    SettingsScreenState,
    _draw_app_settings,
    _handle_settings_key,
    _save_show_debate,
)


# ---------- _save_show_debate persistence ----------


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_save_show_debate_writes_to_yaml_when_persist(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
    }
    _write_yaml(cfg_path, runtime)

    _save_show_debate(runtime, cfg_path, show_debate=False, persist=True)

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    # runtime config also updated
    assert runtime["display"]["show_debate"] is False


def test_save_show_debate_preserves_other_keys(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {
            "name": "House of AI",
            "members": [{"name": "A", "provider": "mock", "model": "mock-v1"}],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    _write_yaml(cfg_path, runtime)

    _save_show_debate(runtime, cfg_path, show_debate=True, persist=True)

    on_disk = _read_yaml(cfg_path)
    assert on_disk["parliament"]["name"] == "House of AI"
    assert on_disk["parliament"]["members"][0]["name"] == "A"
    assert on_disk["providers"]["ollama"]["base_url"] == "http://localhost:11434/v1"
    assert on_disk["display"]["show_debate"] is True


def test_save_show_debate_mock_mode_does_not_write_disk(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {"parliament": {"name": "Mock", "members": []}, "providers": {}}
    # File does NOT exist on disk — mock mode shouldn't create one
    _save_show_debate(runtime, cfg_path, show_debate=False, persist=False)

    assert not cfg_path.exists(), "mock mode must not write to disk"
    # but runtime is updated for the current session
    assert runtime["display"]["show_debate"] is False


def test_save_show_debate_overwrites_existing_value(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
        "display": {"show_debate": True},
    }
    _write_yaml(cfg_path, runtime)

    _save_show_debate(runtime, cfg_path, show_debate=False, persist=True)

    assert _read_yaml(cfg_path)["display"]["show_debate"] is False


# ---------- _handle_settings_key — focus + toggle + save ----------


def _state(save_dir="x", show_debate=True, focus="save_dir") -> SettingsScreenState:
    return SettingsScreenState(save_dir=save_dir, show_debate=show_debate, focus=focus)


def test_enter_returns_save_action():
    s = _state()
    new, action = _handle_settings_key(s, curses.KEY_ENTER)
    assert action == "save"
    assert new == s


def test_tab_cycles_focus_save_dir_to_show_debate():
    s = _state(focus="save_dir")
    new, action = _handle_settings_key(s, 9)  # Tab
    assert action == "continue"
    assert new.focus == "show_debate"


def test_tab_cycles_focus_show_debate_to_save_dir():
    s = _state(focus="show_debate")
    new, _ = _handle_settings_key(s, 9)
    assert new.focus == "save_dir"


def test_down_arrow_cycles_focus():
    s = _state(focus="save_dir")
    new, _ = _handle_settings_key(s, curses.KEY_DOWN)
    assert new.focus == "show_debate"


def test_up_arrow_cycles_focus_backwards():
    s = _state(focus="show_debate")
    new, _ = _handle_settings_key(s, curses.KEY_UP)
    assert new.focus == "save_dir"


def test_space_toggles_show_debate_when_focused_on_toggle():
    s = _state(show_debate=True, focus="show_debate")
    new, action = _handle_settings_key(s, ord(" "))
    assert action == "continue"
    assert new.show_debate is False
    # Toggle again
    again, _ = _handle_settings_key(new, ord(" "))
    assert again.show_debate is True


def test_space_inserts_into_save_dir_when_focused_on_text_field():
    """Space in the text field must remain a literal space, not toggle the bool."""
    s = _state(save_dir="my dir", show_debate=True, focus="save_dir")
    new, _ = _handle_settings_key(s, ord(" "))
    assert new.save_dir == "my dir "
    assert new.show_debate is True  # unchanged


def test_text_input_only_affects_save_dir_field():
    s = _state(save_dir="abc", show_debate=True, focus="save_dir")
    new, _ = _handle_settings_key(s, ord("d"))
    assert new.save_dir == "abcd"


def test_text_input_ignored_on_show_debate_field():
    s = _state(save_dir="abc", show_debate=True, focus="show_debate")
    new, _ = _handle_settings_key(s, ord("z"))
    assert new.save_dir == "abc"  # unchanged
    assert new.show_debate is True  # unchanged


def test_backspace_deletes_in_save_dir_field():
    s = _state(save_dir="abc", focus="save_dir")
    new, _ = _handle_settings_key(s, curses.KEY_BACKSPACE)
    assert new.save_dir == "ab"


# ---------- _draw_app_settings rendering ----------


class _FakeStdscr:
    def __init__(self, height=24, width=80):
        self._h = height
        self._w = width
        self.lines: list[tuple[int, int, str, int]] = []

    def getmaxyx(self):
        return (self._h, self._w)

    def addnstr(self, y, x, text, n, attr=0):
        self.lines.append((y, x, text[:n], attr))

    def addstr(self, y, x, text, attr=0):
        self.lines.append((y, x, text, attr))

    def text(self) -> str:
        return "\n".join(t for _, _, t, _ in self.lines)


def test_settings_screen_renders_save_dir_and_toggle_fields():
    s = _state(save_dir="/tmp/h", show_debate=True, focus="save_dir")
    scr = _FakeStdscr()
    _draw_app_settings(scr, s, 24, 80)
    body = scr.text()
    assert "Hansard save directory" in body
    assert "/tmp/h" in body
    assert "Live debate view" in body or "Show debate" in body


def test_settings_screen_renders_toggle_state_on():
    s = _state(show_debate=True, focus="show_debate")
    scr = _FakeStdscr()
    _draw_app_settings(scr, s, 24, 80)
    body = scr.text()
    # checkbox style: [x]/[✓] for ON
    assert "[x]" in body or "[✓]" in body or "ON" in body


def test_settings_screen_renders_toggle_state_off():
    s = _state(show_debate=False, focus="show_debate")
    scr = _FakeStdscr()
    _draw_app_settings(scr, s, 24, 80)
    body = scr.text()
    assert "[ ]" in body or "OFF" in body


def test_settings_screen_focus_highlights_save_dir_row():
    """When focus=save_dir, the save_dir value row (y=4) is reversed; toggle row (y=7) is not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="save_dir"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[4] & curses.A_REVERSE
    assert not (by_y[7] & curses.A_REVERSE)


def test_settings_screen_focus_highlights_toggle_row():
    """When focus=show_debate, the toggle row (y=7) is reversed; save_dir row (y=4) is not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="show_debate"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[7] & curses.A_REVERSE
    assert not (by_y[4] & curses.A_REVERSE)


def test_settings_screen_help_line_mentions_toggle_keys():
    """The footer/help line must teach users how to operate the toggle."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(), 24, 80)
    body = scr.text().lower()
    assert "tab" in body or "switch" in body
    assert "space" in body or "toggle" in body


# ---------- Integration: settings round-trip via TUI helper ----------


def test_settings_state_initializes_from_config_show_debate_true():
    """Helper that builds the initial state from app_settings + config."""
    config = {"display": {"show_debate": True}}
    state = tui_mod._init_settings_state(save_dir="/tmp/x", config=config)
    assert state.save_dir == "/tmp/x"
    assert state.show_debate is True
    assert state.focus == "save_dir"


def test_settings_state_initializes_from_config_show_debate_false():
    config = {"display": {"show_debate": False}}
    state = tui_mod._init_settings_state(save_dir="/tmp/x", config=config)
    assert state.show_debate is False


def test_settings_state_defaults_show_debate_on_when_display_missing():
    state = tui_mod._init_settings_state(save_dir="/tmp/x", config={})
    assert state.show_debate is True
