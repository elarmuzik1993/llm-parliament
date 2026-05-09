"""Keyboard-driven terminal UI for drafting questions and browsing members."""

from __future__ import annotations

import asyncio
import curses
import json
import os
import re
import sys
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from parliament.commands import COMMANDS, Command, CommandContext, SpeakerOp, dispatch
from parliament.config import (
    KEY_PROVIDERS,
    PARLIAMENT_DIR,
    USER_CONFIG,
    api_key_status,
    build_parliament_from_config,
    load_keys,
    resolve_hansard_level,
    resolve_show_debate,
    save_config,
    save_key,
)
from parliament.render.hansard import HansardLevel
from parliament.core.model_tiers import get_tier, get_tier_label
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard, Member
from parliament.model_catalog import picker_data_for
from parliament.render import build_renderer

SETTINGS_FILE = PARLIAMENT_DIR / "settings.json"
DEFAULT_SAVE_DIR = PARLIAMENT_DIR / "hansards"
SUPPORTED_PROVIDERS = ["ollama", "anthropic", "openai", "google", "mock"]
MEMBER_FIELDS = ["provider", "model", "base_url"]


@dataclass(frozen=True)
class ModelSettings:
    """Display-ready model settings for the TUI."""

    member: Member
    role: str
    api_key_status: str
    base_url: str


@dataclass(frozen=True)
class AppSettings:
    """User-configurable TUI settings."""

    save_dir: str


@dataclass
class SettingsScreenState:
    """In-screen state for the Settings dialog (focus + per-field draft values).

    save_dir lives in settings.json (TUI-only); show_debate and
    hansard.level live in config.yaml.
    """

    save_dir: str
    show_debate: bool
    hansard_level: "HansardLevel"
    focus: str = "save_dir"  # "save_dir" | "hansard_level" | "show_debate"


_SETTINGS_FOCUS_ORDER = ("save_dir", "hansard_level", "show_debate")

_HANSARD_LEVEL_CYCLE = (
    HansardLevel.MINIMAL,
    HansardLevel.VERDICT,
    HansardLevel.ARCHIVE,
    HansardLevel.FULL,
)


def _next_focus(focus: str) -> str:
    idx = _SETTINGS_FOCUS_ORDER.index(focus)
    return _SETTINGS_FOCUS_ORDER[(idx + 1) % len(_SETTINGS_FOCUS_ORDER)]


def _prev_focus(focus: str) -> str:
    idx = _SETTINGS_FOCUS_ORDER.index(focus)
    return _SETTINGS_FOCUS_ORDER[(idx - 1) % len(_SETTINGS_FOCUS_ORDER)]


def _init_settings_state(save_dir: str, config: dict[str, Any]) -> SettingsScreenState:
    """Build the initial Settings-screen state from persisted sources."""
    show_debate = bool(config.get("display", {}).get("show_debate", True))
    raw_level = (config.get("hansard") or {}).get("level")
    hansard_level = HansardLevel.parse(raw_level)
    return SettingsScreenState(
        save_dir=save_dir,
        show_debate=show_debate,
        hansard_level=hansard_level,
        focus="save_dir",
    )


def _cycle_hansard_level(current: HansardLevel, direction: int) -> HansardLevel:
    """Advance through the level cycle by `direction` (±1) with wrap-around."""
    idx = _HANSARD_LEVEL_CYCLE.index(current)
    return _HANSARD_LEVEL_CYCLE[(idx + direction) % len(_HANSARD_LEVEL_CYCLE)]


def _handle_settings_key(
    state: SettingsScreenState, key: int
) -> tuple[SettingsScreenState, str]:
    """Handle a key press on the Settings screen.

    Returns ``(state, action)``. ``action`` is one of:
      - ``"continue"``: keep editing, redraw with new state
      - ``"save"``:     persist and return to dashboard
    Cancel (Backspace/Esc/b) is handled in the outer dispatcher.
    """
    if key in (curses.KEY_ENTER, 10, 13):
        return state, "save"
    if key in (9, curses.KEY_DOWN):  # Tab / Down
        return dataclasses.replace(state, focus=_next_focus(state.focus)), "continue"
    if key == curses.KEY_UP:
        return dataclasses.replace(state, focus=_prev_focus(state.focus)), "continue"
    if state.focus == "hansard_level":
        if key in (curses.KEY_RIGHT, ord(" ")):
            new_level = _cycle_hansard_level(state.hansard_level, +1)
            return dataclasses.replace(state, hansard_level=new_level), "continue"
        if key == curses.KEY_LEFT:
            new_level = _cycle_hansard_level(state.hansard_level, -1)
            return dataclasses.replace(state, hansard_level=new_level), "continue"
        return state, "continue"  # other keys are no-ops on the level field
    if state.focus == "show_debate":
        if key == ord(" "):
            return dataclasses.replace(state, show_debate=not state.show_debate), "continue"
        return state, "continue"
    # focus == "save_dir": delegate to text-input handler
    return dataclasses.replace(state, save_dir=_handle_text_key(state.save_dir, key)), "continue"


def _save_settings(
    runtime_config: dict[str, Any],
    config_path: Path,
    *,
    show_debate: bool,
    hansard_level: "HansardLevel",
    persist: bool = True,
) -> dict[str, Any]:
    """Persist Settings-screen state to YAML config (skipped in mock mode).

    Writes both ``display.show_debate`` and ``hansard.level`` in one
    round-trip via ``_load_editable_config`` + ``save_config`` so that
    unrelated YAML keys (e.g. members, providers) are preserved.
    """
    show_value = bool(show_debate)
    level_value = hansard_level.value

    if persist:
        editable_config = _load_editable_config(config_path, runtime_config)
        editable_config.setdefault("display", {})["show_debate"] = show_value
        editable_config.setdefault("hansard", {})["level"] = level_value
        save_config(editable_config, config_path)

    runtime_config.setdefault("display", {})["show_debate"] = show_value
    runtime_config.setdefault("hansard", {})["level"] = level_value
    return runtime_config


@dataclass
class MemberEditorState:
    """In-TUI state for editing a parliament member."""

    member_index: int
    draft: dict[str, str]
    field_index: int = 0
    mode: str = "form"
    picker_index: int = 0
    picker_kind: str = ""
    picker_options: list[str] | None = None
    picker_notice: str | None = None
    custom_input: str = ""


def load_app_settings() -> AppSettings:
    """Load persisted TUI settings."""
    if not SETTINGS_FILE.exists():
        return AppSettings(save_dir=str(DEFAULT_SAVE_DIR))

    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return AppSettings(save_dir=str(DEFAULT_SAVE_DIR))

    save_dir = data.get("save_dir") or str(DEFAULT_SAVE_DIR)
    return AppSettings(save_dir=str(save_dir))


def save_app_settings(settings: AppSettings) -> None:
    """Persist TUI settings."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"save_dir": settings.save_dir}, indent=2) + "\n",
        encoding="utf-8",
    )


def build_model_settings(
    config: dict[str, Any],
    speaker_override: str | None = None,
) -> list[ModelSettings]:
    """Build settings rows from config without creating provider clients."""
    load_keys()
    provider_configs = config.get("providers", {})
    member_configs = config["parliament"]["members"]
    members = [
        Member(
            name=mc["name"],
            provider_name=mc["provider"],
            model=mc["model"],
            tier=get_tier(mc["model"]),
        )
        for mc in member_configs
    ]
    speaker_name = _speaker_name(members, speaker_override)

    return [
        ModelSettings(
            member=member,
            role=_member_role(member, speaker_name),
            api_key_status=api_key_status(member.provider_name),
            base_url=str(provider_configs.get(member.provider_name, {}).get("base_url", "default")),
        )
        for member in members
    ]


def run_tui(
    settings: list[ModelSettings],
    config: dict[str, Any],
    config_path: Path | None,
    speaker_override: str | None = None,
    mock: bool = False,
) -> None:
    """Run the curses TUI."""
    curses.wrapper(_run, settings, config, config_path, speaker_override, mock)


def _speaker_name(members: list[Member], override: str | None) -> str:
    if override:
        for member in members:
            if member.name.lower() == override.lower():
                return member.name
    top_tier = min(member.tier for member in members)
    return next(member.name for member in members if member.tier == top_tier)


def _member_role(member: Member, speaker_name: str) -> str:
    if member.name == speaker_name:
        return "Speaker / member"
    return "Member"


def _member_base_url(config: dict[str, Any], provider: str) -> str:
    provider_config = config.get("providers", {}).get(provider, {})
    if "base_url" in provider_config:
        return str(provider_config["base_url"])
    if provider == "ollama":
        return "http://localhost:11434/v1"
    return ""


def _member_draft_from_config(config: dict[str, Any], member_index: int) -> MemberEditorState:
    member = config["parliament"]["members"][member_index]
    return MemberEditorState(
        member_index=member_index,
        draft={
            "name": str(member["name"]),
            "provider": str(member["provider"]),
            "model": str(member["model"]),
            "base_url": _member_base_url(config, str(member["provider"])),
        },
    )


def _provider_choices() -> list[str]:
    return SUPPORTED_PROVIDERS[:]


def _normalize_member_draft(draft: dict[str, str]) -> dict[str, str]:
    return {
        "name": draft["name"].strip(),
        "provider": draft["provider"].strip(),
        "model": draft["model"].strip(),
        "base_url": draft["base_url"].strip(),
    }


def _load_editable_config(config_path: Path, fallback_config: dict[str, Any]) -> dict[str, Any]:
    if Path(config_path).exists():
        raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    return fallback_config


def _apply_member_edit(config: dict[str, Any], member_index: int, draft: dict[str, str]) -> None:
    members = config["parliament"]["members"]
    member = members[member_index]
    member["name"] = draft["name"]
    member["provider"] = draft["provider"]
    member["model"] = draft["model"]

    providers = config.setdefault("providers", {})
    if draft["base_url"]:
        provider_config = providers.setdefault(draft["provider"], {})
        provider_config["base_url"] = draft["base_url"]
    elif draft["provider"] == "ollama":
        provider_config = providers.setdefault("ollama", {})
        provider_config["base_url"] = str(_member_base_url(config, "ollama"))


def _disable_terminal_flow_control() -> None:
    """Stop the TTY driver from eating Ctrl-S / Ctrl-Q for XON/XOFF.

    Without this, key 17 (Ctrl-Q) never reaches curses on most Linux
    terminals because the kernel line discipline consumes it. Silently
    no-ops on Windows or non-TTY stdin.
    """
    if not sys.stdin.isatty():
        return
    try:
        import termios

        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[0] &= ~(termios.IXON | termios.IXOFF)
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        # Best-effort; non-Linux or restricted TTY just keep default behavior.
        pass


def _run(
    stdscr,
    settings: list[ModelSettings],
    config: dict[str, Any],
    config_path: Path | None,
    speaker_override: str | None,
    mock: bool = False,
) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        # Some terminals (e.g. legacy Windows cmd.exe) reject cursor toggling.
        pass
    stdscr.keypad(True)
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    _disable_terminal_flow_control()

    active_config_path = Path(config_path) if config_path else USER_CONFIG
    question = ""
    focus = "question"
    selected = 0
    top = 0
    result_top = 0
    screen = "dashboard"
    message = ""
    hansard: Hansard | None = None
    error_message = ""
    result_message = ""
    app_settings = load_app_settings()
    settings_state = _init_settings_state(app_settings.save_dir, config)
    resolved_level = resolve_hansard_level(cli_flag=None, config=config)
    member_editor: MemberEditorState | None = None
    palette_index = 0
    members_expanded = False
    api_key_provider: str | None = None
    api_key_input: str = ""
    api_key_return_screen: str = "dashboard"

    while True:
        height, width = stdscr.getmaxyx()
        stdscr.erase()

        if screen == "dashboard":
            top = _draw_dashboard(
                stdscr,
                settings,
                question,
                focus,
                selected,
                top,
                message,
                height,
                width,
                palette_index,
                members_expanded,
            )
        elif screen == "detail":
            _draw_detail(stdscr, settings[selected], question, height, width)
        elif screen == "edit_member" and member_editor is not None:
            _draw_member_editor(
                stdscr,
                config,
                member_editor,
                speaker_override,
                height,
                width,
            )
        elif screen == "provider_picker" and member_editor is not None:
            _draw_picker(
                stdscr,
                "Choose Provider",
                member_editor.picker_options or _provider_choices(),
                member_editor.picker_index,
                height,
                width,
            )
        elif screen == "model_picker" and member_editor is not None:
            _draw_picker(
                stdscr,
                "Choose Model",
                member_editor.picker_options or [],
                member_editor.picker_index,
                height,
                width,
                footer="Enter: select  c: custom  k: API key  Esc: back",
                notice=member_editor.picker_notice,
            )
        elif screen == "custom_model" and member_editor is not None:
            _draw_custom_input(
                stdscr,
                "Custom Model",
                member_editor.custom_input,
                height,
                width,
            )
        elif screen == "result" and hansard is not None:
            result_top = _draw_result(
                stdscr,
                hansard,
                result_top,
                result_message,
                app_settings.save_dir,
                height,
                width,
            )
        elif screen == "error":
            _draw_error(stdscr, error_message, height, width)
        elif screen == "app_settings":
            _draw_app_settings(stdscr, settings_state, height, width)
        elif screen == "api_key_input" and api_key_provider is not None:
            existing = os.environ.get(KEY_PROVIDERS[api_key_provider], "")
            _draw_api_key_input(
                stdscr,
                api_key_provider,
                api_key_input,
                _mask_api_key(existing),
                height,
                width,
            )

        stdscr.refresh()
        key = stdscr.getch()

        if key == 17:  # Ctrl+Q
            return

        if screen == "dashboard":
            if focus != "question" and key in (ord("q"), ord("Q")):
                return
            if key == 27:  # Esc
                if focus == "question" and question.startswith("/"):
                    question = ""
                    palette_index = 0
                    message = ""
                    continue
                if focus == "members":
                    members_expanded = False
                    focus = "question"
                    continue
                return
            if key == 9:
                if focus == "question":
                    members_expanded = True
                    focus = "members"
                else:
                    focus = "question"
            elif focus == "question":
                palette_open = question.startswith("/") and not message
                palette_matches = _palette_matches(question) if palette_open else []
                if palette_open and palette_matches and key in (curses.KEY_DOWN, curses.KEY_UP):
                    if key == curses.KEY_DOWN:
                        palette_index = (palette_index + 1) % len(palette_matches)
                    else:
                        palette_index = (palette_index - 1) % len(palette_matches)
                    continue
                if key in (curses.KEY_ENTER, 10, 13):
                    stripped = question.strip()
                    if (
                        palette_open
                        and palette_matches
                        and " " not in stripped
                    ):
                        # User picked a command from the palette.
                        idx = min(palette_index, len(palette_matches) - 1)
                        stripped = f"/{palette_matches[idx].name}"
                    if stripped.startswith("/"):
                        ctx = CommandContext(
                            members=[s.member for s in settings],
                            speaker_override=speaker_override,
                            hansard=hansard,
                            save_dir=app_settings.save_dir,
                        )
                        result = dispatch(stripped, ctx)
                        if result.quit:
                            return
                        if result.clear_question:
                            question = ""
                        if result.speaker_op is SpeakerOp.CLEAR:
                            speaker_override = None
                            settings = build_model_settings(config, speaker_override)
                        elif result.speaker_op is SpeakerOp.SET:
                            speaker_override = result.speaker_value
                            settings = build_model_settings(config, speaker_override)
                        if result.clear_hansard:
                            hansard = None
                        if result.toggle_members_panel:
                            members_expanded = not members_expanded
                            if not members_expanded:
                                focus = "question"
                        if result.open_members_picker:
                            members_expanded = True
                            focus = "members"
                            question = ""
                        message = result.message
                        if result.open_screen == "app_settings":
                            settings_state = _init_settings_state(app_settings.save_dir, config)
                            screen = "app_settings"
                        if result.open_key_input:
                            api_key_provider = result.open_key_input
                            api_key_input = ""
                            api_key_return_screen = "dashboard"
                            screen = "api_key_input"
                    elif stripped:
                        message = ""
                        try:
                            hansard = _run_debate(
                                stdscr,
                                stripped,
                                config,
                                speaker_override,
                            )
                            question = ""
                            result_top = 0
                            try:
                                saved_path = save_hansard(hansard, app_settings.save_dir, level=resolved_level)
                                result_message = f"Auto-saved to {saved_path}"
                            except OSError as exc:
                                result_message = f"Auto-save failed: {exc}"
                            screen = "result"
                        except Exception as exc:
                            error_message = str(exc)
                            screen = "error"
                    else:
                        message = "Type a question before pressing Enter."
                else:
                    prev = question
                    question, focus = _handle_question_key(question, key)
                    if question != prev:
                        palette_index = 0
                    message = ""
            elif key in (ord("s"), ord("S")):
                settings_state = _init_settings_state(app_settings.save_dir, config)
                screen = "app_settings"
            elif key in (curses.KEY_DOWN, ord("j")) and selected < len(settings) - 1:
                selected += 1
                focus = "members"
            elif key in (curses.KEY_UP, ord("k")) and selected > 0:
                selected -= 1
                focus = "members"
            elif key in (curses.KEY_ENTER, 10, 13):
                member_editor = _member_draft_from_config(config, selected)
                screen = "edit_member"

        elif screen == "detail":
            if key in (ord("e"), ord("E")):
                member_editor = _member_draft_from_config(config, selected)
                screen = "edit_member"
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
                screen = "dashboard"
            elif key in (ord("q"), ord("Q")):
                return

        elif screen == "edit_member" and member_editor is not None:
            if key in (curses.KEY_LEFT, 27, ord("b"), ord("B")):
                member_editor = None
                screen = "dashboard"
            elif key in (curses.KEY_UP, curses.KEY_DOWN, 9):
                member_editor.field_index = _cycle_index(
                    member_editor.field_index,
                    len(MEMBER_FIELDS),
                    key,
                )
            elif key in (curses.KEY_ENTER, 10, 13):
                field = MEMBER_FIELDS[member_editor.field_index]
                if field == "provider":
                    member_editor.picker_kind = "provider"
                    member_editor.picker_options = _provider_choices()
                    member_editor.picker_index = _current_picker_index(
                        member_editor.picker_options,
                        member_editor.draft["provider"],
                    )
                    screen = "provider_picker"
                elif field == "model":
                    member_editor.picker_kind = "model"
                    options, notice = _model_picker_options(
                        member_editor.draft["provider"],
                        config,
                    )
                    member_editor.picker_options = options
                    member_editor.picker_notice = notice
                    member_editor.picker_index = _current_picker_index(
                        options,
                        member_editor.draft["model"],
                    )
                    screen = "model_picker"
                else:
                    # name or base_url: Enter saves the edit.
                    try:
                        config, settings, selected, message = _commit_member_edit(
                            config, active_config_path, member_editor, speaker_override, mock
                        )
                        member_editor = None
                        screen = "dashboard"
                    except Exception as exc:
                        error_message = str(exc)
                        screen = "error"
            elif key in (19,):  # Ctrl+S
                try:
                    config, settings, selected, message = _commit_member_edit(
                        config, active_config_path, member_editor, speaker_override, mock
                    )
                    member_editor = None
                    screen = "dashboard"
                except Exception as exc:
                    error_message = str(exc)
                    screen = "error"
            else:
                field = MEMBER_FIELDS[member_editor.field_index]
                if field == "base_url":
                    member_editor.draft[field] = _handle_text_key(member_editor.draft[field], key)

        elif screen == "provider_picker" and member_editor is not None:
            if key in (curses.KEY_UP, ord("k")):
                member_editor.picker_index = max(0, member_editor.picker_index - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                member_editor.picker_index = min(
                    len(member_editor.picker_options or []) - 1,
                    member_editor.picker_index + 1,
                )
            elif key in (curses.KEY_ENTER, 10, 13):
                chosen = (member_editor.picker_options or _provider_choices())[member_editor.picker_index]
                member_editor.draft["provider"] = chosen
                member_editor.draft["base_url"] = _member_base_url(config, chosen)
                member_editor.draft["model"] = ""
                member_editor.picker_kind = "model"
                env_var = KEY_PROVIDERS.get(chosen)
                if env_var and not os.environ.get(env_var):
                    api_key_provider = chosen
                    api_key_input = ""
                    api_key_return_screen = "model_picker"
                    member_editor.picker_options = ["__custom__"]
                    member_editor.picker_notice = None
                    member_editor.picker_index = 0
                    screen = "api_key_input"
                else:
                    options, notice = _model_picker_options(chosen, config)
                    member_editor.picker_options = options
                    member_editor.picker_notice = notice
                    member_editor.picker_index = 0
                    screen = "model_picker"
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
                screen = "edit_member"

        elif screen == "model_picker" and member_editor is not None:
            options = member_editor.picker_options or []
            if key in (curses.KEY_UP, ord("k")):
                member_editor.picker_index = max(0, member_editor.picker_index - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                member_editor.picker_index = min(len(options) - 1, member_editor.picker_index + 1)
            elif key in (ord("c"), ord("C")):
                member_editor.custom_input = member_editor.draft["model"]
                screen = "custom_model"
            elif key in (ord("k"), ord("K")):
                provider = member_editor.draft["provider"]
                if provider in KEY_PROVIDERS:
                    api_key_provider = provider
                    api_key_input = ""
                    api_key_return_screen = "model_picker"
                    screen = "api_key_input"
            elif key in (curses.KEY_ENTER, 10, 13):
                if not options:
                    continue
                chosen = options[member_editor.picker_index]
                if chosen == "__custom__":
                    member_editor.custom_input = member_editor.draft["model"]
                    screen = "custom_model"
                else:
                    member_editor.draft["model"] = chosen
                    try:
                        config, settings, selected, message = _commit_member_edit(
                            config, active_config_path, member_editor, speaker_override, mock
                        )
                        member_editor = None
                        screen = "dashboard"
                    except Exception as exc:
                        error_message = str(exc)
                        screen = "error"
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
                screen = "edit_member"

        elif screen == "custom_model" and member_editor is not None:
            if key in (curses.KEY_LEFT, 27, ord("b"), ord("B")):
                screen = "model_picker"
            elif key in (curses.KEY_ENTER, 10, 13):
                if member_editor.custom_input.strip():
                    member_editor.draft["model"] = member_editor.custom_input.strip()
                    try:
                        config, settings, selected, message = _commit_member_edit(
                            config, active_config_path, member_editor, speaker_override, mock
                        )
                        member_editor = None
                        screen = "dashboard"
                    except Exception as exc:
                        error_message = str(exc)
                        screen = "error"
                else:
                    error_message = "Model name cannot be empty."
                    screen = "error"
            else:
                member_editor.custom_input = _handle_text_key(member_editor.custom_input, key)

        elif screen == "api_key_input" and api_key_provider is not None:
            if key in (curses.KEY_LEFT, 27):
                screen = api_key_return_screen
                api_key_input = ""
            elif key in (curses.KEY_ENTER, 10, 13):
                trimmed = api_key_input.strip()
                if not trimmed:
                    api_key_input = ""
                    error_message = "API key cannot be empty."
                    screen = "error"
                else:
                    try:
                        save_key(api_key_provider, trimmed)
                        os.environ[KEY_PROVIDERS[api_key_provider]] = trimmed
                        last4 = trimmed[-4:] if len(trimmed) > 4 else "•" * len(trimmed)
                        message = f"Saved {api_key_provider} API key (•••{last4})."
                        if api_key_return_screen == "model_picker" and member_editor is not None:
                            options, notice = _model_picker_options(
                                member_editor.draft["provider"],
                                config,
                            )
                            member_editor.picker_options = options
                            member_editor.picker_notice = notice
                            member_editor.picker_index = 0
                        if api_key_return_screen == "dashboard":
                            settings = build_model_settings(config, speaker_override)
                        screen = api_key_return_screen
                        api_key_input = ""
                    except OSError as exc:
                        api_key_input = ""
                        error_message = f"Failed to save key: {exc}"
                        screen = "error"
            else:
                api_key_input = _handle_text_key(api_key_input, key)

        elif screen in ("error", "app_settings") and key in (
            curses.KEY_LEFT,
            curses.KEY_BACKSPACE,
            27,
            ord("b"),
            ord("B"),
        ):
            screen = "dashboard"

        elif screen == "result":
            if key in (curses.KEY_DOWN, ord("j")):
                result_top += 1
            elif key in (curses.KEY_UP, ord("k")) and result_top > 0:
                result_top -= 1
            elif key in (ord("s"), ord("S")) and hansard is not None:
                # Auto-save already ran; only retry when it failed.
                if not result_message.startswith("Auto-saved"):
                    try:
                        saved_path = save_hansard(hansard, app_settings.save_dir, level=resolved_level)
                        result_message = f"Saved to {saved_path}"
                    except OSError as exc:
                        result_message = f"Save failed: {exc}"
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
                screen = "dashboard"

        elif screen == "app_settings":
            settings_state, action = _handle_settings_key(settings_state, key)
            if action == "save":
                app_settings = AppSettings(
                    save_dir=settings_state.save_dir.strip() or str(DEFAULT_SAVE_DIR)
                )
                save_app_settings(app_settings)
                config = _save_settings(
                    config,
                    active_config_path,
                    show_debate=settings_state.show_debate,
                    hansard_level=settings_state.hansard_level,
                    persist=not mock,
                )
                live_label = "live view ON" if settings_state.show_debate else "live view OFF"
                level_label = settings_state.hansard_level.value
                if mock:
                    message = f"Settings updated for this session ({live_label} · level: {level_label}; mock mode — not saved)."
                else:
                    message = f"Settings saved ({live_label} · level: {level_label}, save dir: {app_settings.save_dir})."
                screen = "dashboard"


def _handle_question_key(question: str, key: int) -> tuple[str, str]:
    if key in (curses.KEY_DOWN, curses.KEY_UP):
        return question, "members"
    return _handle_text_key(question, key), "question"


def _handle_text_key(value: str, key: int) -> str:
    if key in (curses.KEY_BACKSPACE, 127, 8):
        return value[:-1]
    if key == 21:  # Ctrl+U
        return ""
    if 32 <= key <= 126:
        return value + chr(key)
    return value


def _cycle_index(current: int, count: int, key: int) -> int:
    if count <= 0:
        return 0
    if key in (curses.KEY_UP, curses.KEY_LEFT):
        return (current - 1) % count
    if key in (curses.KEY_DOWN, curses.KEY_RIGHT, 9):
        return (current + 1) % count
    return current


def _current_picker_index(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _model_picker_options(
    provider: str,
    config: dict[str, Any] | None = None,
) -> tuple[list[str], str | None]:
    """Return (picker options, optional notice). Custom is always last."""
    data = picker_data_for(provider, config)
    return data.models + ["__custom__"], data.notice


def _draw_picker(
    stdscr,
    title: str,
    options: list[str],
    selected: int,
    height: int,
    width: int,
    footer: str = "Enter: select  Esc: back",
    notice: str | None = None,
) -> None:
    _add_line(stdscr, 0, 0, title, curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, footer, curses.A_DIM, width)
    notice_lines = notice.splitlines() if notice else []
    notice_height = len(notice_lines)
    for offset, line in enumerate(notice_lines):
        _add_line(stdscr, 3 + offset, 0, line, curses.A_DIM, width)
    list_top = 3 + (notice_height + 1 if notice_height else 0)
    visible = max(1, height - list_top - 1)
    top = max(0, min(selected, max(0, len(options) - visible)))
    for row, option in enumerate(options[top : top + visible], start=list_top):
        idx = top + row - list_top
        label = "Add custom model" if option == "__custom__" else option
        label = f"> {label}" if idx == selected else f"  {label}"
        attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
        _add_line(stdscr, row, 0, label, attr, width)


def _draw_custom_input(
    stdscr,
    title: str,
    value: str,
    height: int,
    width: int,
) -> None:
    _add_line(stdscr, 0, 0, title, curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, "Enter: save  Esc: back  Ctrl+U: clear", curses.A_DIM, width)
    _add_line(stdscr, 3, 0, f" {value or 'Type model name'}", curses.A_REVERSE, width)
    _add_line(stdscr, max(0, height - 2), 0, "Custom models are saved into config as-is.", curses.A_DIM, width)


def _mask_api_key(key: str) -> str:
    """Show only the last 4 chars; mask the rest with bullets."""
    if not key:
        return ""
    if len(key) <= 4:
        return "•" * len(key)
    return "•" * (len(key) - 4) + key[-4:]


def _draw_api_key_input(
    stdscr,
    provider: str,
    value: str,
    existing_masked: str,
    height: int,
    width: int,
) -> None:
    env_var = KEY_PROVIDERS.get(provider, f"{provider.upper()}_API_KEY")
    _add_line(stdscr, 0, 0, f"Set API Key — {provider}", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Enter: save  Esc: back  Ctrl+U: clear",
        curses.A_DIM,
        width,
    )
    _add_line(stdscr, 3, 0, f"Stored as {env_var} in ~/.parliament/keys.env (chmod 0600)", curses.A_DIM, width)
    if existing_masked:
        _add_line(stdscr, 4, 0, f"Existing key: {existing_masked}", curses.A_DIM, width)
    label_y = 6 if existing_masked else 5
    _add_line(stdscr, label_y, 0, "New key (visible)", curses.A_BOLD, width)
    display = value or "Paste or type the API key"
    if len(display) > width - 5:
        display = display[-(width - 5):]
    style = curses.A_REVERSE if value else curses.A_REVERSE | curses.A_DIM
    _add_line(stdscr, label_y + 1, 0, f" {display}", style, width)
    if value:
        _add_line(stdscr, label_y + 3, 0, f"Will be saved as: {_mask_api_key(value)}", curses.A_DIM, width)
    _add_line(
        stdscr,
        max(0, height - 2),
        0,
        "Get a key from the provider's dashboard, then paste it here.",
        curses.A_DIM,
        width,
    )


def _draw_member_editor(
    stdscr,
    config: dict[str, Any],
    editor: MemberEditorState,
    speaker_override: str | None,
    height: int,
    width: int,
) -> None:
    preview_members = _preview_members(config, editor)
    speaker_name = _speaker_name(preview_members, speaker_override)
    preview_member = preview_members[editor.member_index]
    draft = editor.draft
    editable_rows = [
        ("Provider", draft["provider"]),
        ("Model", draft["model"]),
        ("Base URL", draft["base_url"] or "default"),
    ]
    derived_rows = [
        ("Name", draft["name"] or "(set by model)"),
        ("Tier", get_tier_label(preview_member.tier)),
        ("Role", _member_role(preview_member, speaker_name)),
        ("API key", api_key_status(draft["provider"])),
    ]

    title_name = draft["name"] or draft["model"] or "(unnamed)"
    _add_line(stdscr, 0, 0, f"Edit Member: {title_name}", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Up/down/Tab: field  Enter: picker/save  Ctrl+S: save  Esc: cancel",
        curses.A_DIM,
        width,
    )
    _add_line(stdscr, 3, 0, "Editable", curses.A_BOLD, width)
    for idx, (label, value) in enumerate(editable_rows, start=5):
        is_active = MEMBER_FIELDS[idx - 5] == MEMBER_FIELDS[editor.field_index]
        prefix = ">" if is_active else " "
        attr = curses.A_REVERSE if is_active else curses.A_NORMAL
        _add_line(stdscr, idx, 0, f"{prefix} {label:<10} {value}", attr, width)

    preview_y = 5 + len(editable_rows) + 2
    _add_line(stdscr, preview_y, 0, "Derived", curses.A_BOLD, width)
    for idx, (label, value) in enumerate(derived_rows, start=preview_y + 2):
        _add_line(stdscr, idx, 0, f"{label:<10} {value}", curses.A_NORMAL, width)

    _add_line(
        stdscr,
        max(0, height - 2),
        0,
        "Provider and model use pickers; model supports Add custom model.",
        curses.A_DIM,
        width,
    )


def _preview_members(config: dict[str, Any], editor: MemberEditorState) -> list[Member]:
    members: list[Member] = []
    raw_members = config["parliament"]["members"]
    for idx, raw in enumerate(raw_members):
        if idx == editor.member_index:
            draft = editor.draft
            members.append(
                Member(
                    name=draft["name"],
                    provider_name=draft["provider"],
                    model=draft["model"],
                    tier=get_tier(draft["model"]),
                )
            )
        else:
            members.append(
                Member(
                    name=str(raw["name"]),
                    provider_name=str(raw["provider"]),
                    model=str(raw["model"]),
                    tier=get_tier(str(raw["model"])),
                )
            )
    return members


def _autoname_members(members_list: list[dict]) -> None:
    """Rewrite member['name'] to match model, with #2/#3 suffix on duplicates."""
    counts: dict[str, int] = {}
    for member in members_list:
        model = str(member.get("model", "")).strip()
        if not model:
            continue
        n = counts.get(model, 0) + 1
        counts[model] = n
        member["name"] = model if n == 1 else f"{model} #{n}"


def _commit_member_edit(
    runtime_config: dict[str, Any],
    config_path: Path,
    editor: MemberEditorState,
    speaker_override: str | None,
    mock: bool,
) -> tuple[dict[str, Any], list[ModelSettings], int, str]:
    """Save the editor draft and return the new (config, settings, selected, message)."""
    runtime_config = _save_member_edit(
        runtime_config,
        config_path,
        editor,
        persist=not mock,
    )
    settings = build_model_settings(runtime_config, speaker_override)
    message = (
        "Mock mode: edit kept in memory only."
        if mock
        else "Member saved."
    )
    return runtime_config, settings, editor.member_index, message


def _save_member_edit(
    runtime_config: dict[str, Any],
    config_path: Path,
    editor: MemberEditorState,
    persist: bool = True,
) -> dict[str, Any]:
    draft = _normalize_member_draft(editor.draft)
    if draft["provider"] not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown provider '{draft['provider']}'")
    if not draft["model"]:
        raise ValueError("Model cannot be empty.")

    members = runtime_config["parliament"]["members"]
    if editor.member_index >= len(members):
        raise ValueError("Selected member no longer exists.")

    if persist:
        editable_config = _load_editable_config(config_path, runtime_config)
        _apply_member_edit(editable_config, editor.member_index, draft)
        _autoname_members(editable_config["parliament"]["members"])
        save_config(editable_config, config_path)
    _apply_member_edit(runtime_config, editor.member_index, draft)
    _autoname_members(runtime_config["parliament"]["members"])
    editor.draft["name"] = runtime_config["parliament"]["members"][editor.member_index]["name"]
    return runtime_config


def _draw_dashboard(
    stdscr,
    settings: list[ModelSettings],
    question: str,
    focus: str,
    selected: int,
    top: int,
    message: str,
    height: int,
    width: int,
    palette_index: int = 0,
    members_expanded: bool = False,
) -> int:
    _add_line(stdscr, 0, 0, "LLM Parliament", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Enter: run/command  Tab: members  /help: commands  Esc/Ctrl+Q: quit",
        curses.A_DIM,
        width,
    )
    _draw_question(stdscr, question, focus == "question", 3, width)

    palette_visible = focus == "question" and question.startswith("/") and not message
    if palette_visible:
        palette_lines = _command_palette_lines(question)
        matches = _palette_matches(question)
        for offset, line in enumerate(palette_lines):
            if offset == 0:
                attr = curses.A_BOLD
            elif matches and offset - 1 == palette_index:
                attr = curses.A_REVERSE
            else:
                attr = curses.A_DIM
            _add_line(stdscr, 5 + offset, 0, line, attr, width)
        overlay_height = len(palette_lines)
    else:
        message_lines = message.splitlines() if message else []
        for offset, line in enumerate(message_lines):
            attr = curses.A_BOLD if offset == 0 else curses.A_NORMAL
            _add_line(stdscr, 5 + offset, 0, line, attr, width)
        overlay_height = len(message_lines)

    member_top = 8 if overlay_height <= 1 else 5 + overlay_height + 2

    if not members_expanded:
        compact_y = max(member_top - 1, 5 + max(1, overlay_height) + 1)
        _add_line(
            stdscr,
            compact_y,
            0,
            _compact_members_line(settings, width),
            curses.A_DIM,
            width,
        )
        _add_line(
            stdscr,
            compact_y + 1,
            0,
            "Tab or /expand to open members panel",
            curses.A_DIM,
            width,
        )
        return top

    list_width = width
    visible_rows = max(1, height - member_top - 2)
    if selected < top:
        top = selected
    elif selected >= top + visible_rows:
        top = selected - visible_rows + 1

    _add_line(stdscr, member_top - 1, 0, "Parliament Members", curses.A_BOLD, width)
    for row, setting in enumerate(settings[top : top + visible_rows], start=member_top):
        idx = top + row - member_top
        marker = ">" if idx == selected else " "
        member = setting.member
        text = (
            f"{marker} {member.name:<20} {member.provider_name:<10} "
            f"{member.model:<24} {get_tier_label(member.tier):<8}"
        )
        attr = curses.A_REVERSE if idx == selected and focus == "members" else curses.A_NORMAL
        _add_line(stdscr, row, 0, text, attr, list_width)

    if top > 0:
        _add_line(stdscr, member_top - 1, max(0, list_width - 8), "more ^", curses.A_DIM, width)
    if top + visible_rows < len(settings):
        _add_line(stdscr, height - 1, width - 8, "more v", curses.A_DIM, width)

    return top


def _compact_members_line(settings: list[ModelSettings], width: int) -> str:
    rich = "Members: " + " · ".join(
        f"{s.member.name} ({s.member.provider_name}/{s.member.model})" for s in settings
    )
    if len(rich) < width:
        return rich
    medium = "Members: " + " · ".join(
        f"{s.member.name} ({s.member.provider_name})" for s in settings
    )
    if len(medium) < width:
        return medium
    return "Members: " + ", ".join(s.member.name for s in settings)


def _palette_matches(question: str) -> list[Command]:
    """Commands whose name or alias starts with the typed prefix."""
    if not question.startswith("/"):
        return []
    typed = question[1:].split(" ", 1)[0].lower()
    return [
        c
        for c in COMMANDS
        if c.name.startswith(typed) or any(a.startswith(typed) for a in c.aliases)
    ]


def _command_palette_lines(question: str) -> list[str]:
    """Header + filtered command list (no selection highlight)."""
    matches = _palette_matches(question)
    typed = question[1:].split(" ", 1)[0].lower() if question.startswith("/") else ""
    if not matches:
        return [f"No commands match '/{typed}'", "  Press Backspace or type /help"]
    header = "Commands (Up/Down + Enter):" if not typed else f"Commands matching '/{typed}' (Up/Down + Enter):"
    return [header] + [f"  /{c.name:<10} {c.summary}" for c in matches]


def _draw_question(stdscr, question: str, focused: bool, y: int, width: int) -> None:
    attr = curses.A_REVERSE if focused else curses.A_NORMAL
    _add_line(stdscr, y, 0, "Question", curses.A_BOLD, width)
    placeholder = "Type the question you want Parliament to debate"
    value = question or placeholder
    if len(value) > width - 5:
        value = value[-(width - 5):]
    style = attr if question else attr | curses.A_DIM
    _add_line(stdscr, y + 1, 0, f" {value}", style, width)


def _draw_detail(stdscr, setting: ModelSettings, question: str, height: int, width: int) -> None:
    member = setting.member
    rows = _settings_rows(setting)

    _add_line(stdscr, 0, 0, "Model Settings", curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, "Left/backspace/Esc/b: back  q: quit  Ctrl+Q: quit", curses.A_DIM, width)
    _add_line(stdscr, 3, 0, member.name, curses.A_BOLD, width)
    if question:
        _add_line(stdscr, 4, 0, f"Question: {question}", curses.A_DIM, width)

    for idx, (label, value) in enumerate(rows, start=6):
        if idx >= height:
            break
        _add_line(stdscr, idx, 2, f"{label:<10} {value}", curses.A_NORMAL, width)


def _run_debate(
    stdscr,
    question: str,
    config: dict[str, Any],
    speaker_override: str | None,
) -> Hansard:
    members, providers = build_parliament_from_config(config)

    show = resolve_show_debate(cli_flag=None, config=config)
    renderer = build_renderer(show_debate=show, mode="tui", stdscr=stdscr)

    if not show:
        # Preserve the legacy static "Please wait..." screen when the live
        # view is opted out.
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        _add_line(stdscr, 0, 0, "Running Parliament", curses.A_BOLD, width)
        _add_line(stdscr, 2, 0, f"Question: {question}", curses.A_NORMAL, width)
        _add_line(stdscr, 4, 0, "First Reading -> Debate -> Division", curses.A_DIM, width)
        _add_line(stdscr, max(0, height - 2), 0, "Please wait...", curses.A_DIM, width)
        stdscr.refresh()

    parliament = Parliament(
        members=members,
        providers=providers,
        on_progress=renderer.emit,
        speaker_override=speaker_override,
    )
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    with renderer:
        return asyncio.run(parliament.ask(question))


def _draw_result(
    stdscr,
    hansard: Hansard,
    top: int,
    message: str,
    save_dir: str,
    height: int,
    width: int,
) -> int:
    lines = _result_lines(hansard)
    body_top = 2
    body_bottom = max(body_top, height - 3)
    visible = max(1, body_bottom - body_top + 1)
    max_top = max(0, len(lines) - visible)
    top = min(top, max_top)

    _add_line(stdscr, 0, 0, "Verdict", curses.A_BOLD, width)

    for offset, line in enumerate(lines[top : top + visible]):
        attr = curses.A_BOLD if line.isupper() else curses.A_NORMAL
        _add_line(stdscr, body_top + offset, 0, line, attr, width)

    if message:
        _add_line(stdscr, max(0, height - 2), 0, message, curses.A_BOLD, width)

    controls = "Up/down: scroll  b/Esc/backspace: dashboard  q: quit"
    if save_dir and len(controls) + len(save_dir) + 7 < width:
        controls = f"{controls}  Dir: {save_dir}"
    _add_line(stdscr, max(0, height - 1), 0, controls, curses.A_DIM, width)

    if top > 0:
        _add_line(stdscr, 0, max(0, width - 8), "more ^", curses.A_DIM, width)
    if top < max_top:
        _add_line(stdscr, max(0, height - 2), max(0, width - 8), "more v", curses.A_DIM, width)
    return top


def _draw_error(stdscr, error_message: str, height: int, width: int) -> None:
    _add_line(stdscr, 0, 0, "Parliament Error", curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, "b/Esc/backspace: dashboard  q: quit", curses.A_DIM, width)
    _add_line(stdscr, 3, 0, error_message or "Unknown error", curses.A_NORMAL, width)
    if "Connection" in error_message or "connect" in error_message.lower():
        _add_line(stdscr, 5, 0, "Try `parliament --mock` for a no-service test run.", curses.A_DIM, width)
    _add_line(stdscr, max(0, height - 2), 0, "The one-shot CLI is still available with --mock.", curses.A_DIM, width)


def _draw_app_settings(
    stdscr,
    state: "SettingsScreenState",
    height: int,
    width: int,
) -> None:
    """Render the Settings screen with three fields and focus highlight."""
    _add_line(stdscr, 0, 0, "Settings", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Enter: save  Tab: switch  Space: toggle  ←/→: cycle  b/Esc/backspace: cancel",
        curses.A_DIM,
        width,
    )

    # --- Field 1: Hansard save directory ---
    _add_line(stdscr, 3, 0, "Hansard save directory", curses.A_BOLD, width)
    value = state.save_dir or str(DEFAULT_SAVE_DIR)
    if len(value) > width - 5:
        value = value[-(width - 5):]
    save_dir_attr = curses.A_REVERSE if state.focus == "save_dir" else curses.A_NORMAL
    _add_line(stdscr, 4, 0, f" {value}", save_dir_attr, width)

    # --- Field 2: Hansard detail level ---
    _add_line(stdscr, 6, 0, "Hansard detail level", curses.A_BOLD, width)
    cycle_text = " · ".join(
        f"[{lvl.value}]" if lvl is state.hansard_level else lvl.value
        for lvl in _HANSARD_LEVEL_CYCLE
    )
    level_attr = curses.A_REVERSE if state.focus == "hansard_level" else curses.A_NORMAL
    _add_line(stdscr, 7, 0, f" {cycle_text}", level_attr, width)
    _add_line(
        stdscr,
        8,
        0,
        "     minimal: rec only · verdict: + 4-part synthesis · archive: + frontmatter+footer · full: + transcripts",
        curses.A_DIM,
        width,
    )

    # --- Field 3: Live debate view toggle ---
    _add_line(stdscr, 10, 0, "Live debate view", curses.A_BOLD, width)
    box = "[x]" if state.show_debate else "[ ]"
    label = "Show debate as it happens"
    toggle_attr = curses.A_REVERSE if state.focus == "show_debate" else curses.A_NORMAL
    _add_line(stdscr, 11, 0, f" {box} {label}", toggle_attr, width)
    _add_line(
        stdscr,
        12,
        0,
        "     Also: --show-debate / --no-show-debate or PARLIAMENT_SHOW_DEBATE",
        curses.A_DIM,
        width,
    )

    _add_line(
        stdscr,
        max(0, height - 2),
        0,
        "Saved verdicts are written as Markdown Hansard files.",
        curses.A_DIM,
        width,
    )


def save_hansard(
    hansard: Hansard,
    save_dir: str,
    *,
    level: "HansardLevel | None" = None,
) -> Path:
    """Save a Hansard Markdown file at the given level (defaults to VERDICT)."""
    from parliament.render.hansard import HansardLevel as _HL, render_markdown

    resolved_level = level if level is not None else _HL.VERDICT

    directory = Path(save_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(hansard.bill.title or hansard.bill.content)
    path = directory / f"{timestamp}-{slug}-{hansard.id[:8]}.md"
    path.write_text(render_markdown(hansard, resolved_level), encoding="utf-8")
    return path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "parliament-response"


def _result_lines(hansard: Hansard) -> list[str]:
    synthesis = hansard.synthesis
    duration = hansard.duration_ms / 1000
    calls = len(hansard.members) * 2 + 1
    lines = [
        f"Question: {hansard.bill.content}",
        "",
    ]

    for heading, value in (
        ("CONSENSUS", synthesis.consensus),
        ("SPLIT", synthesis.split),
        ("RISKS", synthesis.risks),
        ("RECOMMENDATION", synthesis.recommendation),
    ):
        if value:
            lines.extend([heading, *value.splitlines(), ""])

    lines.extend([
        "-" * 40,
        f"Session: {duration:.1f}s",
        f"Calls: {calls}",
        f"Speaker: {synthesis.speaker_name}",
        f"Hansard: {hansard.id}",
    ])
    return lines


def _settings_rows(setting: ModelSettings) -> list[tuple[str, str]]:
    member = setting.member
    return [
        ("Name", member.name),
        ("Provider", member.provider_name),
        ("Model", member.model),
        ("Tier", get_tier_label(member.tier)),
        ("Role", setting.role),
        ("API key", setting.api_key_status),
        ("Base URL", setting.base_url),
    ]


def _add_line(stdscr, y: int, x: int, text: str, attr: int, width: int) -> None:
    if y < 0 or x < 0:
        return
    height, _ = stdscr.getmaxyx()
    if y >= height:
        return
    available = max(0, width - x - 1)
    if available == 0:
        return
    try:
        stdscr.addnstr(y, x, text, available, attr)
    except curses.error:
        pass
