"""Keyboard-driven terminal UI for drafting questions and browsing members."""

from __future__ import annotations

import curses
import os
from dataclasses import dataclass
from typing import Any

from parliament.config import load_keys
from parliament.core.model_tiers import get_tier, get_tier_label
from parliament.core.types import Member

KEY_PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


@dataclass(frozen=True)
class ModelSettings:
    """Display-ready model settings for the TUI."""

    member: Member
    role: str
    api_key_status: str
    base_url: str


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
            api_key_status=_api_key_status(member.provider_name),
            base_url=str(provider_configs.get(member.provider_name, {}).get("base_url", "default")),
        )
        for member in members
    ]


def run_tui(settings: list[ModelSettings]) -> None:
    """Run the curses TUI."""
    curses.wrapper(_run, settings)


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


def _api_key_status(provider: str) -> str:
    env_var = KEY_PROVIDERS.get(provider)
    if env_var is None:
        return "not required"
    return "configured" if os.environ.get(env_var) else "missing"


def _run(stdscr, settings: list[ModelSettings]) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    question = ""
    focus = "question"
    selected = 0
    top = 0
    screen = "dashboard"

    while True:
        height, width = stdscr.getmaxyx()
        stdscr.erase()

        if screen == "dashboard":
            top = _draw_dashboard(stdscr, settings, question, focus, selected, top, height, width)
        else:
            _draw_detail(stdscr, settings[selected], question, height, width)

        stdscr.refresh()
        key = stdscr.getch()

        if key == 17:  # Ctrl+Q
            return
        if screen == "dashboard":
            if focus != "question" and key in (ord("q"), ord("Q")):
                return
            if key == 9:
                focus = "members" if focus == "question" else "question"
            elif focus == "question":
                question, focus = _handle_question_key(question, key)
            elif key in (curses.KEY_DOWN, ord("j")) and selected < len(settings) - 1:
                selected += 1
                focus = "members"
            elif key in (curses.KEY_UP, ord("k")) and selected > 0:
                selected -= 1
                focus = "members"
            elif key in (curses.KEY_ENTER, 10, 13):
                screen = "detail"
        elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
            screen = "dashboard"
        elif key in (ord("q"), ord("Q")):
            return


def _handle_question_key(question: str, key: int) -> tuple[str, str]:
    if key in (curses.KEY_ENTER, 10, 13):
        return question, "members"
    if key in (curses.KEY_BACKSPACE, 127, 8):
        return question[:-1], "question"
    if key == 21:  # Ctrl+U
        return "", "question"
    if 32 <= key <= 126:
        return question + chr(key), "question"
    if key in (curses.KEY_DOWN, curses.KEY_UP):
        return question, "members"
    return question, "question"


def _draw_dashboard(
    stdscr,
    settings: list[ModelSettings],
    question: str,
    focus: str,
    selected: int,
    top: int,
    height: int,
    width: int,
) -> int:
    _add_line(stdscr, 0, 0, "LLM Parliament", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Tab: switch field  Up/down: models  Enter: settings  Ctrl+U: clear question  Ctrl+Q: quit",
        curses.A_DIM,
        width,
    )
    _draw_question(stdscr, question, focus == "question", 3, width)

    member_top = 8
    settings_x = max(44, width // 2)
    list_width = settings_x - 2 if width >= 80 else width
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
            f"{marker} {member.name:<16} {member.provider_name:<10} "
            f"{member.model:<20} {get_tier_label(member.tier):<8}"
        )
        attr = curses.A_REVERSE if idx == selected and focus == "members" else curses.A_NORMAL
        _add_line(stdscr, row, 0, text, attr, list_width)

    if width >= 80:
        _draw_settings_panel(stdscr, settings[selected], settings_x, member_top - 1, height, width)
    elif height > member_top + len(settings) + 7:
        _draw_settings_panel(stdscr, settings[selected], 0, member_top + visible_rows + 1, height, width)

    if top > 0:
        _add_line(stdscr, member_top - 1, max(0, list_width - 8), "more ^", curses.A_DIM, width)
    if top + visible_rows < len(settings):
        _add_line(stdscr, height - 1, width - 8, "more v", curses.A_DIM, width)

    return top


def _draw_question(stdscr, question: str, focused: bool, y: int, width: int) -> None:
    attr = curses.A_REVERSE if focused else curses.A_NORMAL
    _add_line(stdscr, y, 0, "Question", curses.A_BOLD, width)
    placeholder = "Type the question you want Parliament to debate"
    value = question or placeholder
    if len(value) > width - 5:
        value = value[-(width - 5):]
    style = attr if question else attr | curses.A_DIM
    _add_line(stdscr, y + 1, 0, f" {value}", style, width)


def _draw_settings_panel(
    stdscr,
    setting: ModelSettings,
    x: int,
    y: int,
    height: int,
    width: int,
) -> None:
    member = setting.member
    rows = _settings_rows(setting)
    _add_line(stdscr, y, x, "Settings", curses.A_BOLD, width)
    _add_line(stdscr, y + 1, x, member.name, curses.A_BOLD, width)
    for idx, (label, value) in enumerate(rows, start=y + 3):
        if idx >= height:
            break
        _add_line(stdscr, idx, x, f"{label:<10} {value}", curses.A_NORMAL, width)


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
    if y < 0:
        return
    available = max(0, width - x - 1)
    if available == 0:
        return
    stdscr.addnstr(y, x, text, available, attr)
