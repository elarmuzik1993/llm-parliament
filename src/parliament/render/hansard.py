"""Hansard rendering — levels, section selection, markdown + terminal output.

Public surface:
  - HansardLevel enum (minimal | verdict | archive | full)
  - includes(level, section) — section-inclusion check
  - render_markdown(hansard, level) — Obsidian/GitHub callout markdown
  - render_terminal(hansard, level, console) — Rich panel print

The four levels are strictly monotonic: each level's section set is a
superset of the level below.
"""

from __future__ import annotations

import warnings
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parliament.core.types import Hansard


class HansardLevel(str, Enum):
    """Detail level for Hansard rendering. String-valued for clean YAML."""

    MINIMAL = "minimal"
    VERDICT = "verdict"
    ARCHIVE = "archive"
    FULL = "full"

    @classmethod
    def parse(cls, value: str | None) -> "HansardLevel":
        """Lenient parser: unknown or None values fall back to VERDICT.

        Emits a UserWarning when an unknown non-empty string is passed so
        the user notices typos in CLI flags / env vars / YAML config.
        """
        if value is None:
            return cls.VERDICT
        s = value.strip().lower() if isinstance(value, str) else None
        if not s:
            return cls.VERDICT
        for level in cls:
            if level.value == s:
                return level
        warnings.warn(
            f"Unknown hansard level {value!r}; falling back to {cls.VERDICT.value!r}",
            stacklevel=2,
        )
        return cls.VERDICT


# Section-inclusion matrix — single source of truth for "what's in each level."
# Both render_markdown and render_terminal consume this. Adding a new level
# later = one new entry here; no other changes.
_LEVEL_SECTIONS: dict[HansardLevel, frozenset[str]] = {
    HansardLevel.MINIMAL: frozenset({"question", "recommendation"}),
    HansardLevel.VERDICT: frozenset({"question", "consensus", "split", "risks", "recommendation"}),
    HansardLevel.ARCHIVE: frozenset({
        "frontmatter", "question", "consensus", "split", "risks", "recommendation", "footer",
    }),
    HansardLevel.FULL: frozenset({
        "frontmatter", "question", "consensus", "split", "risks", "recommendation",
        "footer", "first_reading", "debate",
    }),
}


def includes(level: HansardLevel, section: str) -> bool:
    """Whether `section` is included at this detail level."""
    return section in _LEVEL_SECTIONS[level]


# Terminal panel styling — mirrors the markdown callout vocabulary so the
# in-terminal output and the saved .md feel like the same artifact.
# Recommendation gets `bold green` (heavier weight) because it's the
# deliverable; the others are normal-weight color borders.
_PANEL_STYLES: dict[str, tuple[str, str]] = {
    "consensus":      ("ℹ Consensus",      "blue"),
    "split":          ("⚖ Split",          "yellow"),
    "risks":          ("! Risks",          "red"),
    "recommendation": ("✓ Recommendation", "bold green"),
}


def render_markdown(hansard: "Hansard", level: HansardLevel) -> str:
    """Render a Hansard as Markdown with Obsidian/GitHub callouts.

    Section order: frontmatter, question H1, verdict callouts (Consensus →
    Split → Risks → Recommendation), First Reading transcripts, Debate
    transcripts, session footer. Sections are gated by the level's
    inclusion set; empty synthesis sections are omitted (recommendation
    excepted — placeholder fills in).
    """
    parts: list[str] = []

    if includes(level, "frontmatter"):
        parts.append(_render_frontmatter(hansard))

    if includes(level, "question"):
        parts.append(f"# {hansard.bill.content}")
        parts.append("")

    s = hansard.synthesis

    if includes(level, "consensus") and s.consensus.strip():
        parts.append(_callout("info", "Consensus", s.consensus))
    if includes(level, "split") and s.split.strip():
        parts.append(_callout("warning", "Split", s.split))
    if includes(level, "risks") and s.risks.strip():
        parts.append(_callout("danger", "Risks", s.risks))
    if includes(level, "recommendation"):
        body = s.recommendation.strip() or "(no recommendation parsed)"
        parts.append(_callout("success", "Recommendation", body))

    if includes(level, "first_reading"):
        parts.append("## First Reading\n")
        for r in hansard.first_reading:
            parts.append(f"### {r.member_name}\n\n{r.content}\n")

    if includes(level, "debate"):
        parts.append("## Debate\n")
        for r in hansard.debate:
            parts.append(f"### {r.member_name} (critique)\n\n{r.content}\n")

    if includes(level, "footer"):
        parts.append(_render_footer(hansard))

    # Trailing newline; no double-newlines at end.
    return "\n".join(parts).rstrip() + "\n"


def _callout(kind: str, title: str, body: str) -> str:
    """Render an Obsidian/GitHub callout block.

    Body lines are quoted with `> `; blank separator lines are quoted as
    bare `>` so multi-paragraph content renders correctly inside the callout.
    """
    body = body.strip()
    lines = body.split("\n")
    quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
    return f"> [!{kind}] {title}\n{quoted}\n"


def _render_frontmatter(hansard: "Hansard") -> str:
    member_lines = "".join(
        f"  - {m.name} ({m.provider_name}/{m.model})\n" for m in hansard.members
    )
    return (
        "---\n"
        f"id: {hansard.id}\n"
        f"created_at: {hansard.created_at}\n"
        "type: parliament-hansard\n"
        f"speaker: {hansard.synthesis.speaker_name}\n"
        "members:\n"
        f"{member_lines}"
        "---\n"
    )


def _render_footer(hansard: "Hansard") -> str:
    duration = hansard.duration_ms / 1000
    member_count = len(hansard.members)
    calls = member_count * 2 + 1
    speaker = hansard.synthesis.speaker_name
    members = ", ".join(f"{m.name} ({m.provider_name}/{m.model})" for m in hansard.members)
    return (
        "## Session\n\n"
        f"- Speaker: {speaker}\n"
        f"- Members: {members}\n"
        f"- Calls: {calls}\n"
        f"- Duration: {duration:.1f}s\n"
    )


def render_terminal(hansard: "Hansard", level: HansardLevel, console) -> None:
    """Print a Hansard to a Rich console using callout-mirroring panels.

    Side-effect API: writes to `console`. The level governs which sections
    appear; section ordering matches `render_markdown`. Empty sections are
    omitted (recommendation excepted — placeholder fills in).
    """
    from rich.panel import Panel

    s = hansard.synthesis

    if includes(level, "question"):
        console.print()
        console.print(Panel.fit(
            hansard.bill.content,
            title="Parliament Verdict",
            border_style="bright_blue",
        ))
        console.print()

    for section_key in ("consensus", "split", "risks", "recommendation"):
        if not includes(level, section_key):
            continue
        body = getattr(s, section_key)
        if section_key == "recommendation":
            body = (body or "").strip() or "(no recommendation parsed)"
        else:
            body = (body or "").strip()
            if not body:
                continue
        title, style = _PANEL_STYLES[section_key]
        console.print(Panel(body, title=title, border_style=style))

    if includes(level, "first_reading"):
        console.print()
        console.rule("[bold]📖 First Reading[/bold]", style="blue")
        for r in hansard.first_reading:
            console.print(Panel(r.content, title=r.member_name, border_style="cyan"))

    if includes(level, "debate"):
        console.print()
        console.rule("[bold]🗣 Debate[/bold]", style="magenta")
        for r in hansard.debate:
            console.print(Panel(
                r.content,
                title=f"{r.member_name} (critique)",
                border_style="cyan",
            ))

    if includes(level, "footer"):
        _print_terminal_footer(hansard, console)


def _print_terminal_footer(hansard: "Hansard", console) -> None:
    from rich.table import Table
    duration = hansard.duration_ms / 1000
    member_count = len(hansard.members)
    calls = member_count * 2 + 1
    speaker = hansard.synthesis.speaker_name
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column(style="dim")
    summary.add_column(style="dim")
    summary.add_row(
        f"Session: {duration:.1f}s",
        f"Calls: {calls}",
        f"Speaker: {speaker}",
    )
    summary.add_row(
        f"Members: {member_count}",
        f"Hansard: {hansard.id[:8]}",
        "",
    )
    console.print()
    console.print(summary)
