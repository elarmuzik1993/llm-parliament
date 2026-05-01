"""Keyboard-driven terminal UI for drafting questions and browsing members."""

from __future__ import annotations

import asyncio
import curses
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from parliament.config import PARLIAMENT_DIR, build_parliament_from_config, load_keys
from parliament.core.model_tiers import get_tier, get_tier_label
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard, Member

KEY_PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}
SETTINGS_FILE = PARLIAMENT_DIR / "settings.json"
DEFAULT_SAVE_DIR = PARLIAMENT_DIR / "hansards"


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


def load_app_settings() -> AppSettings:
    """Load persisted TUI settings."""
    if not SETTINGS_FILE.exists():
        return AppSettings(save_dir=str(DEFAULT_SAVE_DIR))

    try:
        data = json.loads(SETTINGS_FILE.read_text())
    except json.JSONDecodeError:
        return AppSettings(save_dir=str(DEFAULT_SAVE_DIR))

    save_dir = data.get("save_dir") or str(DEFAULT_SAVE_DIR)
    return AppSettings(save_dir=str(save_dir))


def save_app_settings(settings: AppSettings) -> None:
    """Persist TUI settings."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps({"save_dir": settings.save_dir}, indent=2) + "\n")


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


def run_tui(
    settings: list[ModelSettings],
    config: dict[str, Any],
    speaker_override: str | None = None,
) -> None:
    """Run the curses TUI."""
    curses.wrapper(_run, settings, config, speaker_override)


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


def _run(
    stdscr,
    settings: list[ModelSettings],
    config: dict[str, Any],
    speaker_override: str | None,
) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    question = ""
    focus = "question"
    selected = 0
    top = 0
    result_top = 0
    screen = "dashboard"
    message = ""
    hansard: Hansard | None = None
    error_message = ""
    app_settings = load_app_settings()
    settings_input = app_settings.save_dir
    result_message = ""

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
            )
        elif screen == "detail":
            _draw_detail(stdscr, settings[selected], question, height, width)
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
            _draw_app_settings(stdscr, settings_input, height, width)

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
                if key in (curses.KEY_ENTER, 10, 13):
                    if question.strip():
                        message = ""
                        try:
                            hansard = _run_debate(
                                stdscr,
                                question.strip(),
                                config,
                                speaker_override,
                            )
                            result_top = 0
                            result_message = ""
                            screen = "result"
                        except Exception as exc:
                            error_message = str(exc)
                            screen = "error"
                    else:
                        message = "Type a question before pressing Enter."
                else:
                    question, focus = _handle_question_key(question, key)
                    message = ""
            elif key in (ord("s"), ord("S")):
                settings_input = app_settings.save_dir
                screen = "app_settings"
            elif key in (curses.KEY_DOWN, ord("j")) and selected < len(settings) - 1:
                selected += 1
                focus = "members"
            elif key in (curses.KEY_UP, ord("k")) and selected > 0:
                selected -= 1
                focus = "members"
            elif key in (curses.KEY_ENTER, 10, 13):
                screen = "detail"
        elif screen in ("detail", "error") and key in (
            curses.KEY_LEFT,
            curses.KEY_BACKSPACE,
            27,
            ord("b"),
            ord("B"),
        ):
            screen = "dashboard"
        elif screen == "app_settings" and key in (curses.KEY_LEFT, 27, ord("b"), ord("B")):
            screen = "dashboard"
        elif key in (ord("q"), ord("Q")):
            return
        elif screen == "result":
            if key in (curses.KEY_DOWN, ord("j")):
                result_top += 1
            elif key in (curses.KEY_UP, ord("k")) and result_top > 0:
                result_top -= 1
            elif key in (ord("s"), ord("S")) and hansard is not None:
                try:
                    saved_path = save_hansard(hansard, app_settings.save_dir)
                    result_message = f"Saved to {saved_path}"
                except OSError as exc:
                    result_message = f"Save failed: {exc}"
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 27, ord("b"), ord("B")):
                screen = "dashboard"
        elif screen == "app_settings":
            if key in (curses.KEY_ENTER, 10, 13):
                app_settings = AppSettings(save_dir=settings_input.strip() or str(DEFAULT_SAVE_DIR))
                save_app_settings(app_settings)
                message = f"Save directory set to {app_settings.save_dir}"
                screen = "dashboard"
            else:
                settings_input = _handle_text_key(settings_input, key)


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
) -> int:
    _add_line(stdscr, 0, 0, "LLM Parliament", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        "Enter: run  Tab: members  s: settings from members  Ctrl+U: clear  Ctrl+Q: quit",
        curses.A_DIM,
        width,
    )
    _draw_question(stdscr, question, focus == "question", 3, width)
    if message:
        _add_line(stdscr, 5, 0, message, curses.A_BOLD, width)

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


def _run_debate(
    stdscr,
    question: str,
    config: dict[str, Any],
    speaker_override: str | None,
) -> Hansard:
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    _add_line(stdscr, 0, 0, "Running Parliament", curses.A_BOLD, width)
    _add_line(stdscr, 2, 0, f"Question: {question}", curses.A_NORMAL, width)
    _add_line(stdscr, 4, 0, "First Reading -> Debate -> Division", curses.A_DIM, width)
    _add_line(stdscr, max(0, height - 2), 0, "Please wait...", curses.A_DIM, width)
    stdscr.refresh()

    members, providers = build_parliament_from_config(config)
    parliament = Parliament(
        members=members,
        providers=providers,
        speaker_override=speaker_override,
    )
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
    visible = max(1, height - 4)
    max_top = max(0, len(lines) - visible)
    top = min(top, max_top)

    _add_line(stdscr, 0, 0, "Verdict", curses.A_BOLD, width)
    _add_line(
        stdscr,
        1,
        0,
        f"s: save  Up/down: scroll  b/Esc/backspace: dashboard  q: quit  Dir: {save_dir}",
        curses.A_DIM,
        width,
    )
    if message:
        _add_line(stdscr, 2, 0, message, curses.A_BOLD, width)

    for idx, line in enumerate(lines[top : top + visible], start=4):
        attr = curses.A_BOLD if line.isupper() else curses.A_NORMAL
        _add_line(stdscr, idx, 0, line, attr, width)

    if top > 0:
        _add_line(stdscr, 0, width - 8, "more ^", curses.A_DIM, width)
    if top < max_top:
        _add_line(stdscr, height - 1, width - 8, "more v", curses.A_DIM, width)
    return top


def _draw_error(stdscr, error_message: str, height: int, width: int) -> None:
    _add_line(stdscr, 0, 0, "Parliament Error", curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, "b/Esc/backspace: dashboard  q: quit", curses.A_DIM, width)
    _add_line(stdscr, 3, 0, error_message or "Unknown error", curses.A_NORMAL, width)
    if "Connection" in error_message or "connect" in error_message.lower():
        _add_line(stdscr, 5, 0, "Try `parliament --mock` for a no-service test run.", curses.A_DIM, width)
    _add_line(stdscr, max(0, height - 2), 0, "The one-shot CLI is still available with --mock.", curses.A_DIM, width)


def _draw_app_settings(stdscr, save_dir: str, height: int, width: int) -> None:
    _add_line(stdscr, 0, 0, "Settings", curses.A_BOLD, width)
    _add_line(stdscr, 1, 0, "Enter: save  Ctrl+U: clear  b/Esc/backspace: cancel", curses.A_DIM, width)
    _add_line(stdscr, 3, 0, "Hansard save directory", curses.A_BOLD, width)
    value = save_dir or str(DEFAULT_SAVE_DIR)
    if len(value) > width - 5:
        value = value[-(width - 5):]
    _add_line(stdscr, 4, 0, f" {value}", curses.A_REVERSE, width)
    _add_line(
        stdscr,
        max(0, height - 2),
        0,
        "Saved verdicts are written as Markdown Hansard files.",
        curses.A_DIM,
        width,
    )


def save_hansard(hansard: Hansard, save_dir: str) -> Path:
    """Save a Hansard Markdown file into the configured local directory."""
    directory = Path(save_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(hansard.bill.title or hansard.bill.content)
    path = directory / f"{timestamp}-{slug}-{hansard.id[:8]}.md"
    path.write_text(_hansard_markdown(hansard))
    return path


def _hansard_markdown(hansard: Hansard) -> str:
    synthesis = hansard.synthesis
    duration = hansard.duration_ms / 1000
    calls = len(hansard.members) * 2 + 1
    members = ", ".join(f"{m.name} ({m.provider_name}/{m.model})" for m in hansard.members)

    lines = [
        "---",
        f"id: {hansard.id}",
        f"created_at: {hansard.created_at}",
        "type: parliament-hansard",
        "---",
        "",
        f"# {hansard.bill.title}",
        "",
        "## Question",
        "",
        hansard.bill.content,
        "",
        "## Verdict",
        "",
    ]

    for heading, value in (
        ("Consensus", synthesis.consensus),
        ("Split", synthesis.split),
        ("Risks", synthesis.risks),
        ("Recommendation", synthesis.recommendation),
    ):
        if value:
            lines.extend([f"### {heading}", "", value, ""])

    lines.extend([
        "## First Reading",
        "",
    ])
    for response in hansard.first_reading:
        lines.extend([f"### {response.member_name}", "", response.content, ""])

    lines.extend([
        "## Debate",
        "",
    ])
    for response in hansard.debate:
        lines.extend([f"### {response.member_name}", "", response.content, ""])

    lines.extend([
        "## Session",
        "",
        f"- Speaker: {synthesis.speaker_name}",
        f"- Members: {members}",
        f"- Calls: {calls}",
        f"- Duration: {duration:.1f}s",
        "",
    ])
    return "\n".join(lines)


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
    if y < 0:
        return
    available = max(0, width - x - 1)
    if available == 0:
        return
    stdscr.addnstr(y, x, text, available, attr)
