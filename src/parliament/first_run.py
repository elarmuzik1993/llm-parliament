"""First-run environment detection and config wizard."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from parliament.model_catalog import OllamaModel, fetch_ollama_models
from parliament.presets import Preset, build_mock_preset, select_preset


@dataclass(frozen=True)
class Environment:
    anthropic_key: bool
    openai_key: bool
    google_key: bool
    ollama_reachable: bool
    ollama_models: tuple[OllamaModel, ...]
    total_ram_bytes: int | None


def _system_ram_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.virtual_memory().total)


def detect_environment() -> Environment:
    """Detect first-run provider keys, local models, and RAM."""
    ollama = fetch_ollama_models("http://localhost:11434/v1", timeout=2.0)
    return Environment(
        anthropic_key=bool(os.environ.get("ANTHROPIC_API_KEY")),
        openai_key=bool(os.environ.get("OPENAI_API_KEY")),
        google_key=bool(os.environ.get("GOOGLE_API_KEY")),
        ollama_reachable=not (
            ollama.notice and "not reachable" in ollama.notice.lower()
        ),
        ollama_models=ollama.ollama_models,
        total_ram_bytes=_system_ram_bytes(),
    )


def _format_gb(bytes_value: int | None) -> str:
    if bytes_value is None:
        return "unknown"
    return f"{bytes_value / 1024**3:.0f} GB"


def _print_detected(console: Console, env: Environment, preset: Preset) -> None:
    console.print("Welcome to Parliament. No config found - let's set one up.")
    console.print()
    console.print("Detected:")
    console.print(
        f"  {'✓' if env.anthropic_key else 'ℹ'} ANTHROPIC_API_KEY "
        f"({'configured' if env.anthropic_key else 'not set'})"
    )
    console.print(
        f"  {'✓' if env.openai_key else 'ℹ'} OPENAI_API_KEY "
        f"({'configured' if env.openai_key else 'not set'})"
    )
    console.print(
        f"  {'✓' if env.google_key else 'ℹ'} GOOGLE_API_KEY "
        f"({'configured' if env.google_key else 'not set'})"
    )
    if env.ollama_reachable:
        console.print(f"  ✓ Ollama: reachable ({len(env.ollama_models)} models installed)")
    else:
        console.print("  ℹ Ollama: not reachable")
    console.print(f"  System RAM: {_format_gb(env.total_ram_bytes)}")
    console.print()
    console.print(f"Proposed preset: {preset.name} ({preset.summary})")
    for member in preset.config["parliament"]["members"]:
        console.print(
            f"  - {member['name']} ({member['provider']} / {member['model']})"
        )
    if preset.notice:
        console.print(f"  {preset.notice}")
    console.print()


def _confirm_defaults(console: Console) -> bool:
    console.print("Use these defaults? [Y/n]: ", end="")
    try:
        answer = sys.stdin.readline()
    except EOFError:
        return False
    if answer == "":
        return False
    answer = answer.strip().lower()
    return answer in {"", "y", "yes"}


def _write_preset(path: Path, preset: Preset) -> None:
    from parliament.config import save_config

    save_config(preset.config, path)


def run_first_run_wizard(path: Path) -> Preset:
    """Create a first-run config at `path` and return the preset written."""
    env = detect_environment()
    preset = select_preset(env)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if interactive:
        console = Console()
        _print_detected(console, env, preset)
        if not _confirm_defaults(console):
            preset = build_mock_preset()
        _write_preset(path, preset)
        if preset.name == "mock":
            console.print(
                f"Wrote mock config to {path} - edit it via `parliament` "
                "(TUI member editor)."
            )
        else:
            console.print(f"Wrote config to {path}.")
    else:
        _write_preset(path, preset)
        print(
            f"Created config at {path} (preset: {preset.name}). "
            "Run `parliament doctor` for details.",
            file=sys.stderr,
        )

    return preset
