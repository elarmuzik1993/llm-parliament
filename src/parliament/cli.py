"""CLI frontend — Click commands + Rich output."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import NoReturn

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from parliament import __version__
from parliament.config import (
    KEY_PROVIDERS,
    KEYS_FILE,
    build_parliament_from_config,
    get_keyring_key,
    load_config,
    load_keys,
    migrate_keys_to_keyring,
    remove_key,
    resolve_hansard_level,
    resolve_show_debate,
    save_key,
)
from parliament.core.model_tiers import detect_gap, get_tier_label
from parliament.core.parliament import Parliament
from parliament.providers.base import Provider
from parliament.render import JsonDiagnosticsRenderer, build_renderer
from parliament.render.hansard import HansardLevel, render_terminal

console = (
    Console(force_terminal=True, legacy_windows=False)
    if sys.stdout.isatty()
    else Console()
)

# Diagnostics sink for --json runs: stdout belongs to the JSON document, so
# warnings, failures and errors go to stderr instead. Same TTY handling as
# the stdout singleton above.
err_console = (
    Console(stderr=True, force_terminal=True, legacy_windows=False)
    if sys.stderr.isatty()
    else Console(stderr=True)
)


def _mock_config() -> dict:
    """Return a config that runs entirely against mock providers."""
    return {
        "parliament": {
            "name": "Mock Parliament",
            "members": [
                {"name": "Mock-A", "provider": "mock", "model": "mock-v1"},
                {"name": "Mock-B", "provider": "mock", "model": "mock-v2"},
                {"name": "Mock-C", "provider": "mock", "model": "mock-v3"},
            ],
        },
        "providers": {},
    }


def _mask_key(value: str) -> str:
    """Mask an API key while leaving enough context to identify it."""
    if len(value) <= 10:
        return "****"
    return f"{value[:6]}****{value[-4:]}"


def _configured_keys() -> list[tuple[str, str, str, str]]:
    """Return configured key rows as provider, env var, masked value, source."""
    all_keys = load_keys()
    rows = []

    for provider, env_var in KEY_PROVIDERS.items():
        kr_val = get_keyring_key(env_var)
        in_keyring = kr_val is not None
        # A key present in all_keys but not in keyring came from the file
        in_file = (env_var in all_keys) and not in_keyring

        value = os.environ.get(env_var) or all_keys.get(env_var)
        if not value:
            continue

        if in_file and in_keyring:
            source = "file + keyring"
        elif in_file:
            source = "file"
        elif in_keyring:
            source = "keyring"
        else:
            source = "environment"

        rows.append((provider, env_var, _mask_key(value), source))

    return rows


@click.group(invoke_without_command=True)
@click.version_option(__version__, "-V", "--version")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--speaker", default=None, help="Override Speaker selection in the TUI")
@click.option("--mock", is_flag=True, help="Use mock providers in the TUI")
@click.pass_context
def main(ctx: click.Context, config_path: Path | None, speaker: str | None, mock: bool):
    """LLM Parliament — multi-agent debate for better AI decisions."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        from parliament.tui import build_model_settings, run_tui

        config = _mock_config() if mock else load_config(config_path)
        settings = build_model_settings(config, speaker_override=speaker)
        run_tui(settings, config, config_path, speaker_override=speaker, mock=mock)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        # The message above is the whole explanation -- a missing file needs no
        # traceback -- so the cause is suppressed rather than chained.
        raise SystemExit(1) from None
    except Exception as e:
        # The catch-all is where an unexpected failure lands, so the cause is
        # kept: `Error: {e}` alone is often one line about something three
        # frames down, and the chain is what a bug report needs.
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e


def _ask_error(
    json_output: bool, message: str, *, cause: BaseException | None = None
) -> NoReturn:
    """Print an `ask` failure and exit 1.

    Errors can be raised before the per-run diagnostics console is bound (a bad
    config path, say), so the stream is picked from the flag rather than from a
    local. Under --json this keeps stdout a clean JSON document: a consumer
    piping to jq gets the message on stderr and a non-zero exit, not a parse
    error.

    ``cause`` decides whether the `SystemExit` carries the error that caused it.
    The default is to suppress: for the failures that already print a complete
    explanation -- a missing config file, an uninstalled SDK -- a chained
    traceback is noise. Callers that catch a genuinely unexpected error pass
    ``cause=e`` instead, because there ``Error: {e}`` is usually one line about
    something three frames down and the chain is what a bug report needs.

    Passing this explicitly matters because implicit chaining would otherwise
    make the choice for us: a bare ``raise`` inside a helper called from an
    ``except`` block sets ``__context__`` on every path, friendly or not.
    """
    (err_console if json_output else console).print(message)
    raise SystemExit(1) from cause


@main.command()
@click.argument("question")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--speaker", default=None, help="Override Speaker selection")
@click.option(
    "--hansard",
    "hansard_flag",
    type=click.Choice(["minimal", "verdict", "archive", "full"], case_sensitive=False),
    default=None,
    help="Hansard detail level (default: verdict; override with config or PARLIAMENT_HANSARD_LEVEL)",
)
@click.option("--verbose", is_flag=True, help="Alias for --hansard=full (back-compat)")
@click.option(
    "--show-debate/--no-show-debate",
    "show_debate",
    default=None,
    help="Show the debate process live (default: on; override with config or PARLIAMENT_SHOW_DEBATE)",
)
@click.option("--mock", is_flag=True, help="Use mock providers (dev/testing)")
@click.option("--json", "json_output", is_flag=True, help="Print the full Hansard as JSON")
def ask(
    question: str,
    config_path: Path | None,
    speaker: str | None,
    hansard_flag: str | None,
    verbose: bool,
    show_debate: bool | None,
    mock: bool,
    json_output: bool,
):
    """Ask Parliament a question."""
    try:
        if mock:
            from parliament.core.types import Member
            from parliament.providers.mock import MockProvider

            members = [
                Member(name="Mock-A", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Mock-B", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Mock-C", provider_name="mock", model="mock-v1", tier=3),
            ]
            providers: dict[str, Provider] = {
                "Mock-A": MockProvider(model="mock-v1"),
                "Mock-B": MockProvider(model="mock-v2"),
                "Mock-C": MockProvider(model="mock-v3"),
            }
            config = {}
        else:
            config = load_config(config_path)
            members, providers = build_parliament_from_config(config)

        # Resolve Hansard detail level: CLI > env > config > default(verdict).
        # --verbose is a back-compat alias for --hansard=full, but only when
        # --hansard wasn't passed explicitly.
        level = resolve_hansard_level(cli_flag=hansard_flag, config=config)
        if verbose and hansard_flag is None:
            level = HansardLevel.FULL

        show = resolve_show_debate(cli_flag=show_debate, config=config)
        # Under --json stdout carries the Hansard document, so diagnostics are
        # routed to stderr and the live debate view is dropped entirely.
        diag = err_console if json_output else console
        renderer = (
            JsonDiagnosticsRenderer(console=err_console)
            if json_output
            else build_renderer(show_debate=show, mode="cli", console=console)
        )

        p = Parliament(
            members=members,
            providers=providers,
            on_progress=renderer.emit,
            speaker_override=speaker,
        )

        for warning in p.check_gaps():
            diag.print(f"[yellow]Warning: {warning}[/yellow]")

        if not json_output:
            member_names = " | ".join(m.name for m in members)
            bill = question if len(question) <= 100 else question[:97].rstrip() + "..."
            console.print()
            console.print(Panel.fit(
                f"[bold]Question[/bold]\n{bill}\n\n[dim]Members: {member_names}[/dim]",
                title="Parliament Session",
                border_style="bright_blue",
            ))
            console.print()

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        with renderer:
            try:
                hansard = asyncio.run(p.ask(question))
            except (KeyboardInterrupt, asyncio.CancelledError):
                # CancelledError is a BaseException, so it would otherwise
                # miss the `except Exception` below and escape as a traceback.
                diag.print("[yellow]Debate cancelled.[/yellow]")
                # Asked for, not a failure, so there is no cause to carry.
                raise SystemExit(130) from None

        if json_output:
            click.echo(hansard.to_json())
        else:
            render_terminal(hansard, level, console)

    except FileNotFoundError as e:
        _ask_error(json_output, f"[red]Error: {e}[/red]")
    except ImportError as e:
        _ask_error(json_output, f"[red]{e}[/red]")
    except Exception as e:
        _ask_error(json_output, f"[red]Error: {e}[/red]", cause=e)


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def members(config_path: Path | None):
    """Show parliament composition."""
    try:
        config = load_config(config_path)
        member_list, _ = build_parliament_from_config(config)
    except Exception as e:
        # The catch-all is where an unexpected failure lands, so the cause is
        # kept: `Error: {e}` alone is often one line about something three
        # frames down, and the chain is what a bug report needs.
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e

    table = Table(title="Parliament Members", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Tier")

    for m in member_list:
        table.add_row(m.name, m.provider_name, m.model, get_tier_label(m.tier))

    console.print(table)

    if detect_gap(member_list):
        console.print("[yellow]Warning: large capability gap between members[/yellow]")


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--speaker", default=None, help="Override Speaker selection")
@click.option("--mock", is_flag=True, help="Use mock providers (dev/testing)")
def tui(config_path: Path | None, speaker: str | None, mock: bool):
    """Browse models and settings in an interactive terminal UI."""
    try:
        from parliament.tui import build_model_settings, run_tui

        config = _mock_config() if mock else load_config(config_path)
        settings = build_model_settings(config, speaker_override=speaker)
        run_tui(settings, config, config_path, speaker_override=speaker, mock=mock)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        # The message above is the whole explanation -- a missing file needs no
        # traceback -- so the cause is suppressed rather than chained.
        raise SystemExit(1) from None
    except Exception as e:
        # The catch-all is where an unexpected failure lands, so the cause is
        # kept: `Error: {e}` alone is often one line about something three
        # frames down, and the chain is what a bug report needs.
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e


@main.group()
def keys():
    """Manage API keys."""
    pass


@keys.command("set")
@click.argument("provider", type=click.Choice(list(KEY_PROVIDERS)))
@click.argument("key")
def keys_set(provider: str, key: str):
    """Save an API key to the OS keyring (or keys.env if keyring is unavailable)."""
    storage = save_key(provider, key)
    env_var = KEY_PROVIDERS[provider]
    if storage == "keyring":
        console.print(f"[green]Saved {provider} key[/green] [dim]({env_var} → OS keyring)[/dim]")
    else:
        console.print(f"[green]Saved {provider} key[/green] [dim]({env_var} → {KEYS_FILE})[/dim]")


@keys.command("list")
def keys_list():
    """Show configured API keys (masked)."""
    rows = _configured_keys()
    if not rows:
        console.print(f"[dim]No API keys configured. Keys file: {KEYS_FILE}[/dim]")
        return

    table = Table(title="API Keys")
    table.add_column("Provider", style="bold")
    table.add_column("Environment Variable")
    table.add_column("Key")
    table.add_column("Source")

    for provider, env_var, masked, source in rows:
        table.add_row(provider, env_var, masked, source)

    console.print(table)


@keys.command("remove")
@click.argument("provider", type=click.Choice(list(KEY_PROVIDERS)))
def keys_remove(provider: str):
    """Remove an API key from keys.env and OS keyring."""
    if remove_key(provider):
        console.print(f"[green]Removed {provider} key[/green]")
    else:
        console.print(f"[yellow]{provider} key not found[/yellow]")


@keys.command("migrate")
def keys_migrate():
    """Migrate API keys from keys.env to the OS keyring."""
    if not KEYS_FILE.exists():
        console.print(f"[dim]No {KEYS_FILE} found — nothing to migrate.[/dim]")
        return

    console.print(f"Migrating keys from [dim]{KEYS_FILE}[/dim] to OS keyring …")
    results = migrate_keys_to_keyring()

    if not results:
        console.print("[dim]No keys found in keys.env.[/dim]")
        return

    all_ok = True
    for env_var, status in results.items():
        if status == "migrated":
            console.print(f"  [green]✓[/green] {env_var}")
        else:
            console.print(f"  [red]✗[/red] {env_var} — keyring unavailable")
            all_ok = False

    if all_ok:
        bak = KEYS_FILE.parent / "keys.env.bak"
        console.print(f"\n[dim]Backed up original → {bak}[/dim]")
        console.print("[green]Migration complete.[/green] Run [bold]parliament keys list[/bold] to verify.")
    else:
        console.print(f"\n[yellow]Some keys could not be migrated. {KEYS_FILE} preserved.[/yellow]")


@main.command()
def doctor():
    """Run install health checks (Python version, providers, Ollama, etc.)."""
    from parliament.doctor import run_doctor

    exit_code = run_doctor(console)
    raise SystemExit(exit_code)


@main.command()
def update():
    """Pull the latest code from the editable git tree backing this install."""
    from parliament.commands import CommandContext, _update

    # CLI invocation has no live members/hansard state; pass a stub context.
    ctx = CommandContext(members=[], speaker_override=None, hansard=None, save_dir="")
    result = _update("", ctx)

    if result.message:
        # Print a green check on success (quit=True signals success), red on failure.
        if result.quit:
            console.print(f"[green]✓[/green] {result.message}")
            raise SystemExit(0)
        console.print(f"[red]✗[/red] {result.message}")
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
