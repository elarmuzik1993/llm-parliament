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
    _save_settings,
)


# ---------- helpers ----------


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _state(save_dir="x", show_debate=True, hansard_level=None, focus="save_dir", editing=False) -> SettingsScreenState:
    from parliament.render.hansard import HansardLevel
    if hansard_level is None:
        hansard_level = HansardLevel.VERDICT
    return SettingsScreenState(
        save_dir=save_dir,
        show_debate=show_debate,
        hansard_level=hansard_level,
        focus=focus,
        editing=editing,
    )


# ---------- _save_settings persistence ----------


def test_save_settings_writes_to_yaml_when_persist(tmp_path):
    from parliament.render.hansard import HansardLevel

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.VERDICT,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "verdict"
    assert runtime["display"]["show_debate"] is False


def test_save_settings_preserves_other_keys(tmp_path):
    from parliament.render.hansard import HansardLevel

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {
            "name": "House of AI",
            "members": [{"name": "A", "provider": "mock", "model": "mock-v1"}],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=True,
        hansard_level=HansardLevel.FULL,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["parliament"]["name"] == "House of AI"
    assert on_disk["parliament"]["members"][0]["name"] == "A"
    assert on_disk["providers"]["ollama"]["base_url"] == "http://localhost:11434/v1"
    assert on_disk["display"]["show_debate"] is True
    assert on_disk["hansard"]["level"] == "full"


def test_save_settings_mock_mode_does_not_write_disk(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {"parliament": {"name": "Mock", "members": []}, "providers": {}}

    from parliament.render.hansard import HansardLevel

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.MINIMAL,
        persist=False,
    )

    assert not cfg_path.exists()
    assert runtime["display"]["show_debate"] is False
    assert runtime["hansard"]["level"] == "minimal"


def test_save_settings_overwrites_existing_values(tmp_path):
    from parliament.render.hansard import HansardLevel

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
        "display": {"show_debate": True},
        "hansard": {"level": "minimal"},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.ARCHIVE,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "archive"


def test_save_settings_writes_both_show_debate_and_hansard_level(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {"parliament": {"name": "X", "members": []}, "providers": {}}
    _write_yaml(cfg_path, runtime)

    from parliament.render.hansard import HansardLevel

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.ARCHIVE,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "archive"
    assert runtime["display"]["show_debate"] is False
    assert runtime["hansard"]["level"] == "archive"


# ---------- _handle_settings_key — focus + toggle + save ----------


def test_enter_returns_save_action():
    # Enter saves when focused on a non-text field (hansard_level / show_debate).
    # On save_dir it enters edit mode instead (see test_enter_starts_edit_mode).
    s = _state(focus="hansard_level")
    new, action = _handle_settings_key(s, curses.KEY_ENTER)
    assert action == "save"
    assert new == s


def test_enter_starts_edit_mode_on_save_dir():
    s = _state(focus="save_dir")
    new, action = _handle_settings_key(s, curses.KEY_ENTER)
    assert action == "continue"
    assert new.editing is True


def test_enter_while_editing_exits_edit_mode():
    s = _state(focus="save_dir", editing=True)
    new, action = _handle_settings_key(s, curses.KEY_ENTER)
    assert action == "continue"
    assert new.editing is False


def test_tab_cycles_through_three_fields():
    s1 = _state(focus="save_dir")
    s2, _ = _handle_settings_key(s1, 9)
    assert s2.focus == "hansard_level"
    s3, _ = _handle_settings_key(s2, 9)
    assert s3.focus == "show_debate"
    s4, _ = _handle_settings_key(s3, 9)
    assert s4.focus == "save_dir"


def test_down_arrow_cycles_focus():
    s = _state(focus="save_dir")
    new, _ = _handle_settings_key(s, curses.KEY_DOWN)
    assert new.focus == "hansard_level"


def test_up_arrow_cycles_focus_backwards():
    s = _state(focus="show_debate")
    new, _ = _handle_settings_key(s, curses.KEY_UP)
    assert new.focus == "hansard_level"


def test_right_arrow_cycles_hansard_level_forward():
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")  # default level=VERDICT
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.ARCHIVE
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.FULL
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.MINIMAL  # wraps


def test_left_arrow_cycles_hansard_level_backward():
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")
    s, _ = _handle_settings_key(s, curses.KEY_LEFT)
    assert s.hansard_level is HansardLevel.MINIMAL  # wraps from VERDICT


def test_space_on_hansard_field_cycles_forward():
    """Space behaves the same as right arrow when the level field is focused."""
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")
    s, _ = _handle_settings_key(s, ord(" "))
    assert s.hansard_level is HansardLevel.ARCHIVE


def test_arrows_on_save_dir_field_dont_cycle_level():
    """Left/Right arrows on save_dir should be a no-op (text fields don't cycle)."""
    from parliament.render.hansard import HansardLevel
    s = _state(focus="save_dir")  # default level=VERDICT
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.VERDICT  # unchanged
    assert s.focus == "save_dir"


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
    s = _state(save_dir="my dir", show_debate=True, focus="save_dir", editing=True)
    new, _ = _handle_settings_key(s, ord(" "))
    assert new.save_dir == "my dir "
    assert new.show_debate is True  # unchanged


def test_text_input_only_affects_save_dir_field():
    s = _state(save_dir="abc", show_debate=True, focus="save_dir", editing=True)
    new, _ = _handle_settings_key(s, ord("d"))
    assert new.save_dir == "abcd"


def test_text_input_ignored_on_show_debate_field():
    s = _state(save_dir="abc", show_debate=True, focus="show_debate")
    new, _ = _handle_settings_key(s, ord("z"))
    assert new.save_dir == "abc"  # unchanged
    assert new.show_debate is True  # unchanged


def test_backspace_deletes_in_save_dir_field():
    s = _state(save_dir="abc", focus="save_dir", editing=True)
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
    """When focus=save_dir, the save_dir value row (y=4) is reversed; other field rows are not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="save_dir"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[4] & curses.A_REVERSE
    assert not (by_y[7] & curses.A_REVERSE)   # hansard_level row
    assert not (by_y[11] & curses.A_REVERSE)  # show_debate row


def test_settings_screen_focus_highlights_toggle_row():
    """When focus=show_debate, the toggle row (y=11) is reversed; others not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="show_debate"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[11] & curses.A_REVERSE
    assert not (by_y[4] & curses.A_REVERSE)
    assert not (by_y[7] & curses.A_REVERSE)


def test_settings_screen_help_line_mentions_toggle_keys():
    """The footer/help line must teach users how to operate the toggle."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(), 24, 80)
    body = scr.text().lower()
    assert "tab" in body or "switch" in body
    assert "space" in body or "toggle" in body


def test_settings_screen_renders_hansard_level_cycle(make_hansard=None):
    """Settings screen draws the level cycle widget with current bracketed."""
    from parliament.render.hansard import HansardLevel
    scr = _FakeStdscr()
    state = _state(hansard_level=HansardLevel.VERDICT, focus="hansard_level")
    _draw_app_settings(scr, state, 24, 80)
    body = scr.text()
    # All four levels appear inline; current is bracketed.
    assert "minimal" in body
    assert "[verdict]" in body
    assert "archive" in body
    assert "full" in body


def test_settings_screen_focus_highlights_hansard_level_row():
    from parliament.render.hansard import HansardLevel
    scr = _FakeStdscr()
    _draw_app_settings(
        scr,
        _state(hansard_level=HansardLevel.VERDICT, focus="hansard_level"),
        24,
        80,
    )
    by_y = {y: attr for y, _, _, attr in scr.lines}
    # The level value row is reversed when focused; save_dir row is not.
    # (Find the y position by looking for the bracketed level token.)
    level_row_y = next(
        y for y, _, t, _ in scr.lines if "[verdict]" in t
    )
    assert by_y[level_row_y] & curses.A_REVERSE


def test_settings_screen_renders_each_level_bracketed_in_turn():
    from parliament.render.hansard import HansardLevel
    for lvl in (HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL):
        scr = _FakeStdscr()
        _draw_app_settings(scr, _state(hansard_level=lvl), 24, 80)
        body = scr.text()
        assert f"[{lvl.value}]" in body
        # Other three levels appear without brackets
        for other in (HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL):
            if other is lvl:
                continue
            assert f"[{other.value}]" not in body
            assert other.value in body  # but the bare name still appears


# ---------- Integration: settings round-trip via TUI helper ----------


def test_settings_state_includes_hansard_level():
    from parliament.render.hansard import HansardLevel
    state = tui_mod._init_settings_state(save_dir="/tmp/x", config={})
    assert state.hansard_level is HansardLevel.VERDICT  # default


def test_settings_state_loads_hansard_level_from_config():
    from parliament.render.hansard import HansardLevel
    state = tui_mod._init_settings_state(
        save_dir="/tmp/x",
        config={"hansard": {"level": "archive"}},
    )
    assert state.hansard_level is HansardLevel.ARCHIVE


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
