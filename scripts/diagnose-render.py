#!/usr/bin/env python3
"""Diagnose color + spinner rendering in the user's actual terminal.

Run this directly in a real terminal (no pipes, no redirects):

    cd <repo-root>
    source .venv/bin/activate           # or: .venv\Scripts\Activate.ps1 on Windows
    python scripts/diagnose-render.py

It reports what Rich detects, then renders one sample of each colored
callout panel and a 12-second slow-pace spinner demo so you can see (or
not see) both effects clearly.
"""

from __future__ import annotations

import os
import sys
import time

from rich.console import Console
from rich.panel import Panel

from parliament.core.types import ProgressEvent, Response
from parliament.render.cli_live import RichLiveRenderer


def main() -> int:
    console = Console()

    # 1. Environment detection ------------------------------------------------
    console.print()
    console.rule("[bold]1. What Rich sees about your terminal[/bold]", style="bright_blue")
    console.print()
    console.print(f"  is_terminal:  {console.is_terminal}")
    console.print(f"  color_system: {console.color_system}")
    console.print(f"  encoding:     {console.encoding}")
    console.print(f"  size:         {console.size}")
    console.print(f"  $TERM:        {os.environ.get('TERM', '(unset)')}")
    console.print(f"  $COLORTERM:   {os.environ.get('COLORTERM', '(unset)')}")
    console.print(f"  $NO_COLOR:    {os.environ.get('NO_COLOR', '(unset)')}")
    console.print(f"  sys.stdout:   {sys.stdout!r}")
    console.print()

    if not console.is_terminal:
        console.print(
            "[red bold]is_terminal is False[/red bold] — Rich won't render colors or "
            "engage Live. This is the root cause if you see plain text without "
            "panel borders or animation. Check whether you're piping output, "
            "running through a wrapper, or have a $TERM that confuses Rich."
        )
        console.print()

    # 2. Color sample ---------------------------------------------------------
    console.rule("[bold]2. Color sample — expected: 4 colored panel borders[/bold]", style="bright_blue")
    console.print()
    console.print(Panel("Should be blue", title="ℹ Consensus", border_style="blue"))
    console.print(Panel("Should be yellow", title="⚖ Split", border_style="yellow"))
    console.print(Panel("Should be red", title="! Risks", border_style="red"))
    console.print(Panel("Should be bold green", title="✓ Recommendation", border_style="bold green"))
    console.print()
    console.print(
        "[dim]If those four panel borders are all the same color (e.g. all white "
        "or all dim), your terminal isn't rendering color codes. Check $TERM and "
        "your terminal emulator's color settings.[/dim]"
    )
    console.print()

    # 3. Spinner demo ---------------------------------------------------------
    console.rule(
        "[bold]3. Spinner demo — expected: 3 spinner rows ticking with elapsed timer[/bold]",
        style="bright_blue",
    )
    console.print()
    console.print(
        "[dim]Three members start 'thinking' simultaneously. Each row should show "
        "an animated spinner + member name + elapsed seconds counting up. Rows "
        "disappear as members complete. Total demo: ~12 seconds.[/dim]"
    )
    console.print()

    r = RichLiveRenderer(console=console)
    with r:
        for name in ("Alpha", "Beta", "Gamma"):
            r.emit(ProgressEvent(phase="first_reading", member_name=name, kind="started"))

        time.sleep(7)
        r.emit(ProgressEvent(
            phase="first_reading", member_name="Beta", kind="completed",
            response=Response(member_name="Beta", content="Beta finished first.",
                              phase="first_reading"),
            duration_ms=7000,
        ))

        time.sleep(3)
        r.emit(ProgressEvent(
            phase="first_reading", member_name="Alpha", kind="completed",
            response=Response(member_name="Alpha", content="Alpha finished second.",
                              phase="first_reading"),
            duration_ms=10000,
        ))

        time.sleep(2)
        r.emit(ProgressEvent(
            phase="first_reading", member_name="Gamma", kind="completed",
            response=Response(member_name="Gamma", content="Gamma finished last.",
                              phase="first_reading"),
            duration_ms=12000,
        ))

    console.print()
    console.rule("[bold]Done[/bold]", style="bright_blue")
    console.print()
    console.print(
        "Tell me which of the three sections rendered correctly:\n"
        "  1 — environment line says is_terminal=True and color_system is named\n"
        "  2 — four panels above have visibly different colored borders\n"
        "  3 — you saw spinner rows ticking with elapsed counters before each "
        "completion message scrolled past"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
