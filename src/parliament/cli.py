"""CLI frontend — Click commands + Rich output."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from parliament.config import (
    build_parliament_from_config,
    load_config,
    load_keys,
    save_key,
    remove_key,
)
from parliament.core.model_tiers import get_tier_label, detect_gap
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard

console = Console()


def _make_progress_callback(status: dict):
    """Return a callback that updates a shared status dict for Rich display."""
    def on_progress(phase: str, member: str, state: str):
        status[f"{phase}:{member}"] = state
    return on_progress


def _render_synthesis(hansard: Hansard) -> None:
    """Print the structured synthesis."""
    s = hansard.synthesis
    console.print()
    console.rule("[bold]VERDICT[/bold]", style="bright_yellow")
    console.print()

    if s.consensus:
        console.print("[bold cyan]CONSENSUS[/bold cyan]")
        console.print(s.consensus)
        console.print()

    if s.split:
        console.print("[bold yellow]SPLIT[/bold yellow]")
        console.print(s.split)
        console.print()

    if s.risks:
        console.print("[bold red]RISKS[/bold red]")
        console.print(s.risks)
        console.print()

    if s.recommendation:
        console.print("[bold green]RECOMMENDATION[/bold green]")
        console.print(s.recommendation)
        console.print()

    console.rule(style="dim")
    duration = hansard.duration_ms / 1000
    members = len(hansard.members)
    calls = members * 2 + 1
    speaker = hansard.synthesis.speaker_name
    console.print(
        f"[dim]Session: {duration:.1f}s | {calls} calls | "
        f"Speaker: {speaker} | {members} members[/dim]"
    )


def _render_verbose(hansard: Hansard) -> None:
    """Print full debate transcript before the synthesis."""
    console.print()
    console.rule("[bold]FIRST READING[/bold]", style="blue")
    for r in hansard.first_reading:
        console.print(Panel(r.content, title=r.member_name, border_style="blue"))

    console.rule("[bold]DEBATE[/bold]", style="magenta")
    for r in hansard.debate:
        console.print(Panel(r.content, title=f"{r.member_name} (critique)", border_style="magenta"))


@click.group()
def main():
    """LLM Parliament — multi-agent debate for better AI decisions."""
    pass


@main.command()
@click.argument("question")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--speaker", default=None, help="Override Speaker selection")
@click.option("--verbose", is_flag=True, help="Show full debate transcript")
@click.option("--mock", is_flag=True, help="Use mock providers (dev/testing)")
def ask(question: str, config_path: Path | None, speaker: str | None, verbose: bool, mock: bool):
    """Ask Parliament a question."""
    try:
        if mock:
            from parliament.providers.mock import MockProvider
            from parliament.core.types import Member

            members = [
                Member(name="Mock-A", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Mock-B", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Mock-C", provider_name="mock", model="mock-v1", tier=3),
            ]
            providers = {
                "Mock-A": MockProvider(model="mock-v1"),
                "Mock-B": MockProvider(model="mock-v2"),
                "Mock-C": MockProvider(model="mock-v3"),
            }
        else:
            config = load_config(config_path)
            members, providers = build_parliament_from_config(config)

        p = Parliament(
            members=members,
            providers=providers,
            speaker_override=speaker,
        )

        # Show warnings
        for warning in p.check_gaps():
            console.print(f"[yellow]Warning: {warning}[/yellow]")

        # Show session header
        member_names = " . ".join(m.name for m in members)
        console.print("\n[bold]PARLIAMENT SESSION[/bold]")
        console.print(f"[dim]Members: {member_names}[/dim]")
        console.print(f"[dim]Bill: {question[:80]}[/dim]\n")

        # Windows: SelectorEventLoop required for asyncio + openai/httpx
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        # Run
        with console.status("[bold]First Reading...[/bold]"):
            hansard = asyncio.run(p.ask(question))

        if verbose:
            _render_verbose(hansard)

        _render_synthesis(hansard)

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def members(config_path: Path | None):
    """Show parliament composition."""
    try:
        config = load_config(config_path)
        member_list, _ = build_parliament_from_config(config)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    table = Table(title="Parliament Members")
    table.add_column("Name", style="bold")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Tier")

    for m in member_list:
        table.add_row(m.name, m.provider_name, m.model, get_tier_label(m.tier))

    console.print(table)

    if detect_gap(member_list):
        console.print("[yellow]Warning: large capability gap between members[/yellow]")


@main.group()
def keys():
    """Manage API keys."""
    pass


@keys.command("set")
@click.argument("provider", type=click.Choice(["anthropic", "openai", "google"]))
@click.argument("key")
def keys_set(provider: str, key: str):
    """Save an API key."""
    save_key(provider, key)
    console.print(f"[green]Saved {provider} key[/green]")


@keys.command("list")
def keys_list():
    """Show configured API keys (masked)."""
    loaded = load_keys()
    if not loaded:
        console.print("[dim]No keys configured. Keys file: {KEYS_FILE}[/dim]")
        return

    for var, value in loaded.items():
        masked = value[:6] + "****" + value[-4:] if len(value) > 10 else "****"
        console.print(f"  {var}: {masked}")


@keys.command("remove")
@click.argument("provider", type=click.Choice(["anthropic", "openai", "google"]))
def keys_remove(provider: str):
    """Remove an API key."""
    if remove_key(provider):
        console.print(f"[green]Removed {provider} key[/green]")
    else:
        console.print(f"[yellow]{provider} key not found[/yellow]")


if __name__ == "__main__":
    main()
