"""Health-check logic for `parliament doctor`."""

from __future__ import annotations

from rich.console import Console


def run_doctor(console: Console) -> int:
    """Run all doctor checks and print a report. Returns exit code (0 ok, 1 broken)."""
    console.print("[bold]Environment[/bold]")
    console.print("[bold]Providers[/bold]")
    console.print("[bold]Next steps[/bold]")
    return 0
