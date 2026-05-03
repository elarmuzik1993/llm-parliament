"""Slash-command registry and dispatch for the TUI."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable

from parliament.core.types import Hansard, Member


class SpeakerOp(Enum):
    LEAVE = auto()
    CLEAR = auto()
    SET = auto()


@dataclass(frozen=True)
class CommandContext:
    """Read-only snapshot the TUI hands to handlers."""

    members: list[Member]
    speaker_override: str | None
    hansard: Hansard | None
    save_dir: str


@dataclass
class CommandResult:
    """What a handler asks the TUI to do after dispatch."""

    message: str = ""
    quit: bool = False
    open_screen: str | None = None
    clear_question: bool = True
    speaker_op: SpeakerOp = SpeakerOp.LEAVE
    speaker_value: str | None = None
    clear_hansard: bool = False
    toggle_members_panel: bool = False
    open_members_picker: bool = False
    open_key_input: str | None = None


Handler = Callable[[str, CommandContext], CommandResult]


@dataclass(frozen=True)
class Command:
    name: str
    summary: str
    handler: Handler
    aliases: tuple[str, ...] = field(default_factory=tuple)


def dispatch(text: str, ctx: CommandContext) -> CommandResult:
    """Parse a /command line and run it. Catches handler errors."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return CommandResult(message="Not a command.", clear_question=False)
    name, _, args = stripped[1:].partition(" ")
    cmd = _resolve(name)
    if cmd is None:
        return CommandResult(
            message=f"Unknown command: /{name}. Try /help.",
            clear_question=False,
        )
    try:
        return cmd.handler(args.strip(), ctx)
    except Exception as exc:  # noqa: BLE001 - keep TUI alive on bad handler
        return CommandResult(message=f"Command failed: {exc}", clear_question=False)


def _resolve(name: str) -> Command | None:
    key = name.lower()
    for cmd in COMMANDS:
        if cmd.name == key or key in cmd.aliases:
            return cmd
    return None


def _help(_args: str, _ctx: CommandContext) -> CommandResult:
    lines = ["Available commands:"]
    for cmd in COMMANDS:
        lines.append(f"  /{cmd.name:<10} {cmd.summary}")
    return CommandResult(message="\n".join(lines))


def _quit(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(quit=True)


def _clear(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(message="")


def _reset(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(
        message="Reset.",
        speaker_op=SpeakerOp.CLEAR,
        clear_hansard=True,
    )


def _speaker(args: str, ctx: CommandContext) -> CommandResult:
    if not args:
        current = ctx.speaker_override or "(default: top tier member)"
        return CommandResult(
            message=f"Current speaker: {current}",
            clear_question=False,
        )
    match = next(
        (m.name for m in ctx.members if m.name.lower() == args.lower()),
        None,
    )
    if match is None:
        names = ", ".join(m.name for m in ctx.members)
        return CommandResult(
            message=f"No member named '{args}'. Choose from: {names}",
            clear_question=False,
        )
    return CommandResult(
        message=f"Speaker set to {match}.",
        speaker_op=SpeakerOp.SET,
        speaker_value=match,
    )


def _model(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(open_members_picker=True)


def _settings(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(open_screen="app_settings")


CLOUD_KEY_PROVIDERS = ("anthropic", "openai", "google")


def _key(args: str, _ctx: CommandContext) -> CommandResult:
    if not args:
        return CommandResult(
            message=f"Usage: /key <{'|'.join(CLOUD_KEY_PROVIDERS)}>",
            clear_question=False,
        )
    # Use only the first token so we never echo a key that the user
    # accidentally typed inline (e.g. "/key openai sk-secret").
    parts = args.split()
    provider = parts[0].lower()
    if provider not in CLOUD_KEY_PROVIDERS:
        return CommandResult(
            message=f"Unknown provider '{provider}'. Choose: {', '.join(CLOUD_KEY_PROVIDERS)}.",
            clear_question=False,
        )
    if len(parts) > 1:
        return CommandResult(
            open_key_input=provider,
            message="Tip: paste the key into the input screen, not on the command line.",
        )
    return CommandResult(open_key_input=provider)


def _expand(_args: str, _ctx: CommandContext) -> CommandResult:
    return CommandResult(toggle_members_panel=True)


def _history(args: str, ctx: CommandContext) -> CommandResult:
    n = 10
    if args:
        try:
            n = max(1, int(args))
        except ValueError:
            return CommandResult(message=f"Invalid count: {args}", clear_question=False)
    save_dir = Path(ctx.save_dir).expanduser()
    if not save_dir.exists():
        return CommandResult(message=f"No saved verdicts at {save_dir}")
    files = sorted(save_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    if not files:
        return CommandResult(message=f"No saved verdicts at {save_dir}")
    lines = [f"Last {len(files)} saved verdict(s):"]
    for f in files:
        lines.append(f"  {f.name}")
    return CommandResult(message="\n".join(lines))


def _copy(_args: str, ctx: CommandContext) -> CommandResult:
    if ctx.hansard is None:
        return CommandResult(
            message="No verdict to copy yet. Run a debate first.",
            clear_question=False,
        )
    from parliament.tui import _hansard_markdown

    md = _hansard_markdown(ctx.hansard)
    if _copy_to_clipboard(md):
        return CommandResult(message="Verdict copied to clipboard.")
    return CommandResult(
        message="Clipboard tool not found (install xclip/xsel/wl-copy, or use macOS/Windows).",
    )


def _copy_to_clipboard(text: str) -> bool:
    candidates = [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["wl-copy"],
        ["pbcopy"],
        ["clip"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                text=True,
                check=False,
                timeout=2,
                capture_output=True,
            )
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


COMMANDS: list[Command] = [
    Command("help", "Show this list", _help, aliases=("?",)),
    Command("quit", "Exit the TUI", _quit, aliases=("exit",)),
    Command("clear", "Clear the question field", _clear),
    Command("reset", "Clear question, speaker, and last verdict", _reset),
    Command("speaker", "Set speaker for next debate: /speaker <name>", _speaker),
    Command(
        "model",
        "Open members panel: arrows to scroll, Enter to edit",
        _model,
        aliases=("members",),
    ),
    Command("settings", "Open app settings", _settings),
    Command("key", "Set API key for cloud provider: /key <anthropic|openai|google>", _key),
    Command(
        "expand",
        "Show/hide the full members panel",
        _expand,
        aliases=("collapse", "panel"),
    ),
    Command("history", "List last N saved verdicts: /history [N]", _history),
    Command("copy", "Copy last verdict to system clipboard", _copy),
]
