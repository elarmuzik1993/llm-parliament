# Hansard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the maximalist Hansard format with a four-level detail system (`minimal` / `verdict` / `archive` / `full`) using Obsidian/GitHub callouts in the saved `.md` file and Rich-panel mirrors in the post-run terminal print, with `verdict` as the new compact default. The level applies to both the saved file and the post-run terminal output. The live in-flight view is unchanged.

**Architecture:** A single new module `src/parliament/render/hansard.py` owns `HansardLevel`, the section-inclusion matrix, `render_markdown`, and `render_terminal`. A new `resolve_hansard_level` helper in `config.py` mirrors the existing `resolve_show_debate` precedence (CLI > env > config > default). The TUI Settings screen gains a third focusable field (a 4-state inline cycle widget) alongside the existing save_dir and show_debate fields. The legacy `_save_show_debate` helper is renamed to `_save_settings` and persists both `display.show_debate` and `hansard.level` in one round-trip. `--verbose` survives as an alias for `--hansard=full`.

**Tech Stack:** Python 3.11+, Click 8 (CLI flags), Rich 13 (terminal panels), PyYAML (config), pytest 8 + pytest-asyncio (testing), curses (TUI), ruff (lint).

**Spec:** [`docs/superpowers/specs/2026-05-09-hansard-redesign-design.md`](../specs/2026-05-09-hansard-redesign-design.md)

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `src/parliament/render/hansard.py` | `HansardLevel` enum, section-inclusion matrix, `render_markdown`, `render_terminal` |
| `tests/conftest.py` | Shared `make_hansard` fixture used by all new test files |
| `tests/test_hansard_level.py` | `HansardLevel.parse`, `includes()`, monotonic-hierarchy invariant |
| `tests/test_resolve_hansard_level.py` | CLI > env > config > default precedence |
| `tests/test_render_markdown.py` | Markdown output per level, callout syntax, empty-section omission |
| `tests/test_render_terminal.py` | Rich panel output per level, border styles, titles |

### Modified files

| Path | Changes |
|---|---|
| `src/parliament/config.py` | Add `resolve_hansard_level` (sibling of `resolve_show_debate`) |
| `src/parliament/cli.py` | Add `--hansard` Click option; rewire `ask()` to call `render_terminal`; delete `_render_synthesis` and `_render_verbose`; keep `--verbose` as alias |
| `src/parliament/tui.py` | Extend `SettingsScreenState` with `hansard_level`; rename `_save_show_debate` → `_save_settings`; update `_init_settings_state`, `_handle_settings_key`, `_draw_app_settings`; thread `level` into `save_hansard`; delete `_hansard_markdown` |
| `tests/test_cli.py` | Add `--hansard` flag tests, env var tests, `--verbose` alias test |
| `tests/test_tui_settings_screen.py` | Add cycle-widget tests; update for renamed `_save_settings` |
| `tests/test_tui.py` | Rewrite `test_save_hansard_writes_markdown` against new verdict-default output; add full-level back-compat case |
| `config.example.yaml`, `config.cloud.yaml`, `config.mixed.yaml` | Add `hansard:\n  level: verdict` block with comments |
| `README.md` | New "Hansard detail levels" subsection under Usage |
| `RELEASING.md` | Note this as a behavior change in the next release |

---

## Task 1: HansardLevel enum + parse

**Files:**
- Create: `src/parliament/render/hansard.py`
- Test: `tests/test_hansard_level.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hansard_level.py
"""HansardLevel enum, parse, and section-inclusion matrix."""
from __future__ import annotations

import warnings

import pytest

from parliament.render.hansard import HansardLevel


def test_levels_exist():
    assert HansardLevel.MINIMAL.value == "minimal"
    assert HansardLevel.VERDICT.value == "verdict"
    assert HansardLevel.ARCHIVE.value == "archive"
    assert HansardLevel.FULL.value == "full"


def test_levels_are_string_enums():
    """HansardLevel inherits from str so YAML serialization is trivial."""
    assert isinstance(HansardLevel.VERDICT, str)
    assert HansardLevel.VERDICT == "verdict"


@pytest.mark.parametrize("raw,expected", [
    ("minimal", HansardLevel.MINIMAL),
    ("verdict", HansardLevel.VERDICT),
    ("archive", HansardLevel.ARCHIVE),
    ("full", HansardLevel.FULL),
    ("VERDICT", HansardLevel.VERDICT),
    ("  full  ", HansardLevel.FULL),
])
def test_parse_known_values(raw, expected):
    assert HansardLevel.parse(raw) is expected


def test_parse_none_returns_verdict_default():
    assert HansardLevel.parse(None) is HansardLevel.VERDICT


def test_parse_unknown_returns_verdict_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = HansardLevel.parse("nonsense")
    assert result is HansardLevel.VERDICT
    assert any("nonsense" in str(w.message) for w in caught)


def test_parse_empty_string_returns_verdict():
    assert HansardLevel.parse("") is HansardLevel.VERDICT
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_hansard_level.py -x
```

Expected: ImportError ("cannot import name 'HansardLevel' from 'parliament.render.hansard'") or ModuleNotFoundError ("No module named 'parliament.render.hansard'").

- [ ] **Step 3: Write minimal implementation**

```python
# src/parliament/render/hansard.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_hansard_level.py -v
```

Expected: all 11 tests pass (includes parametrize expansion).

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_hansard_level.py
git commit -m "feat(hansard): HansardLevel enum + lenient parser"
```

---

## Task 2: Section-inclusion matrix + monotonic invariant

**Files:**
- Modify: `src/parliament/render/hansard.py` (add matrix + `includes`)
- Modify: `tests/test_hansard_level.py` (add inclusion + invariant tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hansard_level.py`:

```python
from parliament.render.hansard import includes


def test_minimal_includes_only_question_and_recommendation():
    assert includes(HansardLevel.MINIMAL, "question")
    assert includes(HansardLevel.MINIMAL, "recommendation")
    assert not includes(HansardLevel.MINIMAL, "consensus")
    assert not includes(HansardLevel.MINIMAL, "split")
    assert not includes(HansardLevel.MINIMAL, "risks")
    assert not includes(HansardLevel.MINIMAL, "frontmatter")


def test_verdict_includes_full_synthesis_block():
    for section in ("question", "consensus", "split", "risks", "recommendation"):
        assert includes(HansardLevel.VERDICT, section), section
    assert not includes(HansardLevel.VERDICT, "frontmatter")
    assert not includes(HansardLevel.VERDICT, "footer")
    assert not includes(HansardLevel.VERDICT, "first_reading")


def test_archive_adds_frontmatter_and_footer_only():
    assert includes(HansardLevel.ARCHIVE, "frontmatter")
    assert includes(HansardLevel.ARCHIVE, "footer")
    assert not includes(HansardLevel.ARCHIVE, "first_reading")
    assert not includes(HansardLevel.ARCHIVE, "debate")


def test_full_includes_everything():
    for section in (
        "frontmatter", "question", "consensus", "split", "risks",
        "recommendation", "footer", "first_reading", "debate",
    ):
        assert includes(HansardLevel.FULL, section), section


def test_levels_are_monotonic():
    """Each level's section set must be a superset of the level below."""
    from parliament.render.hansard import _LEVEL_SECTIONS
    levels = [HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL]
    for lower, higher in zip(levels, levels[1:]):
        assert _LEVEL_SECTIONS[lower] <= _LEVEL_SECTIONS[higher], (
            f"{higher.value} must include all sections of {lower.value}"
        )


def test_unknown_section_returns_false():
    assert not includes(HansardLevel.FULL, "nonsense_section")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_hansard_level.py -x
```

Expected: ImportError on `_LEVEL_SECTIONS` and `includes`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/parliament/render/hansard.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_hansard_level.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_hansard_level.py
git commit -m "feat(hansard): section-inclusion matrix with monotonic levels"
```

---

## Task 3: `resolve_hansard_level` precedence helper

**Files:**
- Modify: `src/parliament/config.py` (add helper)
- Create: `tests/test_resolve_hansard_level.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_resolve_hansard_level.py
"""Precedence rules for the --hansard / env / config / default level toggle."""

from __future__ import annotations

import pytest

from parliament.config import resolve_hansard_level
from parliament.render.hansard import HansardLevel


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)


def test_default_is_verdict_when_nothing_set():
    assert resolve_hansard_level(cli_flag=None, config={}) is HansardLevel.VERDICT


def test_cli_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "minimal")
    assert resolve_hansard_level(cli_flag="full", config={}) is HansardLevel.FULL


def test_cli_flag_wins_over_config():
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag="minimal", config=cfg) is HansardLevel.MINIMAL


def test_env_wins_over_config_when_cli_unset(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "full")
    cfg = {"hansard": {"level": "minimal"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.FULL


def test_config_used_when_cli_and_env_unset():
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.ARCHIVE


def test_missing_hansard_section_falls_back_to_default():
    assert resolve_hansard_level(cli_flag=None, config={"parliament": {}}) is HansardLevel.VERDICT


def test_hansard_present_but_level_missing_falls_back_to_default():
    assert resolve_hansard_level(cli_flag=None, config={"hansard": {}}) is HansardLevel.VERDICT


@pytest.mark.parametrize("env_val,expected", [
    ("minimal", HansardLevel.MINIMAL),
    ("VERDICT", HansardLevel.VERDICT),
    ("  archive  ", HansardLevel.ARCHIVE),
    ("Full", HansardLevel.FULL),
])
def test_env_normalization(monkeypatch, env_val, expected):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", env_val)
    assert resolve_hansard_level(cli_flag=None, config={}) is expected


def test_invalid_cli_flag_falls_back_to_default():
    """Unknown CLI value is normalized via HansardLevel.parse, which falls back to VERDICT."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert resolve_hansard_level(cli_flag="nonsense", config={}) is HansardLevel.VERDICT


def test_yaml_string_value_works(monkeypatch):
    """YAML naturally parses 'archive' as a string; helper must accept that."""
    cfg = {"hansard": {"level": "archive"}}
    assert resolve_hansard_level(cli_flag=None, config=cfg) is HansardLevel.ARCHIVE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_resolve_hansard_level.py -x
```

Expected: ImportError on `resolve_hansard_level`.

- [ ] **Step 3: Implement `resolve_hansard_level` in `config.py`**

Add to `src/parliament/config.py` (right after `resolve_show_debate`):

```python
def resolve_hansard_level(*, cli_flag: str | None, config: dict[str, Any]):
    """Decide the Hansard detail level for this run.

    Precedence: CLI flag > PARLIAMENT_HANSARD_LEVEL env var > config
    `hansard.level` > default `verdict`. Unknown values normalise to
    `verdict` via `HansardLevel.parse`.
    """
    # Local import to avoid circular dependency: parliament.render.hansard
    # imports from parliament.core.types (which is fine), but we keep
    # config.py free of render package imports at module-load time.
    from parliament.render.hansard import HansardLevel

    if cli_flag is not None:
        return HansardLevel.parse(cli_flag)
    env = os.environ.get("PARLIAMENT_HANSARD_LEVEL")
    if env is not None:
        return HansardLevel.parse(env)
    raw = (config.get("hansard") or {}).get("level")
    return HansardLevel.parse(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_resolve_hansard_level.py -v
```

Expected: all 14 tests pass (11 named + 3 parametrize expansions, minus param overlap = 14 IDs).

- [ ] **Step 5: Verify the existing suite still passes**

```bash
python -m pytest -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/parliament/config.py tests/test_resolve_hansard_level.py
git commit -m "feat(config): resolve_hansard_level precedence helper"
```

---

## Task 4: Shared `make_hansard` test fixture

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the fixture**

```python
# tests/conftest.py
"""Shared pytest fixtures for parliament tests."""

from __future__ import annotations

import pytest

from parliament.core.types import Bill, Hansard, Member, Response, Synthesis


@pytest.fixture
def make_hansard():
    """Build a deterministic Hansard with controllable section content.

    Pass empty strings for any synthesis section to test omission paths.
    Members default to a 3-member mock parliament; pass an explicit list
    to override.
    """
    def _factory(
        *,
        question: str = "Should we use Postgres or MongoDB?",
        consensus: str = "All members agree relational structure fits.",
        split: str = "Disagreement on whether to plan sharding now.",
        risks: str = "- Schema migration overhead\n- Read scaling under load",
        recommendation: str = "Postgres. ACID + JSON columns + ecosystem maturity.",
        members: list[Member] | None = None,
        first_reading_content: str = "First-reading content body.",
        debate_content: str = "Debate critique content body.",
        speaker_name: str | None = None,
        duration_ms: int = 12_345,
        hansard_id: str = "12345678-aaaa-bbbb-cccc-deadbeef0000",
        created_at: str = "2026-05-09T12:00:00+00:00",
    ) -> Hansard:
        if members is None:
            members = [
                Member(name="Alpha", provider_name="mock", model="mock-v1", tier=3),
                Member(name="Beta", provider_name="mock", model="mock-v2", tier=3),
                Member(name="Gamma", provider_name="mock", model="mock-v3", tier=3),
            ]
        speaker = speaker_name or members[0].name

        first_reading = [
            Response(
                member_name=m.name,
                content=f"{first_reading_content} ({m.name})",
                phase="first_reading",
                duration_ms=1000,
            )
            for m in members
        ]
        debate = [
            Response(
                member_name=m.name,
                content=f"{debate_content} ({m.name})",
                phase="debate",
                duration_ms=1500,
            )
            for m in members
        ]
        synthesis = Synthesis(
            speaker_name=speaker,
            consensus=consensus,
            split=split,
            risks=risks,
            recommendation=recommendation,
            raw=f"CONSENSUS:\n{consensus}\n\nSPLIT:\n{split}\n\nRISKS:\n{risks}\n\nRECOMMENDATION:\n{recommendation}",
        )

        return Hansard(
            bill=Bill(content=question),
            members=members,
            first_reading=first_reading,
            debate=debate,
            synthesis=synthesis,
            id=hansard_id,
            created_at=created_at,
            duration_ms=duration_ms,
        )

    return _factory
```

- [ ] **Step 2: Verify the fixture loads cleanly**

```bash
python -m pytest --collect-only tests/ -q 2>&1 | tail -3
```

Expected: collection completes without errors; total test count unchanged from before this task.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: shared make_hansard fixture for hansard renderer tests"
```

---

## Task 5: `render_markdown` — minimal level

**Files:**
- Modify: `src/parliament/render/hansard.py`
- Create: `tests/test_render_markdown.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render_markdown.py
"""Markdown rendering — Obsidian/GitHub callouts, level-gated sections."""

from __future__ import annotations

import re

from parliament.render.hansard import HansardLevel, render_markdown


def test_minimal_renders_question_h1_and_recommendation_callout(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "# Should we use Postgres or MongoDB?" in md
    assert "> [!success] Recommendation" in md
    assert "Postgres. ACID + JSON columns" in md


def test_minimal_omits_consensus_split_risks(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "[!info] Consensus" not in md
    assert "[!warning] Split" not in md
    assert "[!danger] Risks" not in md


def test_minimal_omits_frontmatter_and_footer(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "---" not in md.split("\n", 5)[0]  # no YAML opener as first line
    assert "## Session" not in md
    assert "id:" not in md.split("# ", 1)[0]  # no frontmatter before H1


def test_minimal_omits_transcripts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "## First Reading" not in md
    assert "## Debate" not in md
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_render_markdown.py -x
```

Expected: ImportError on `render_markdown`.

- [ ] **Step 3: Implement `render_markdown` (minimal level only)**

Append to `src/parliament/render/hansard.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parliament.core.types import Hansard


def render_markdown(hansard: "Hansard", level: HansardLevel) -> str:
    """Render a Hansard as Markdown with Obsidian/GitHub callouts.

    Verdict-block ordering inside the file: Consensus → Split → Risks →
    Recommendation (recommendation last). Empty sections are omitted for
    everything except recommendation, which is always rendered (with a
    placeholder if the Speaker's parser produced an empty string).
    """
    parts: list[str] = []

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_render_markdown.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_render_markdown.py
git commit -m "feat(hansard): render_markdown supports minimal level"
```

---

## Task 6: `render_markdown` — verdict callouts in correct order

**Files:**
- Modify: `tests/test_render_markdown.py`

(No source change needed — the verdict-level branches are already in `render_markdown` from Task 5; this task locks the contract with tests.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_markdown.py`:

```python
def test_verdict_renders_all_four_callouts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.VERDICT)
    assert "> [!info] Consensus" in md
    assert "> [!warning] Split" in md
    assert "> [!danger] Risks" in md
    assert "> [!success] Recommendation" in md


def test_verdict_callouts_appear_in_canonical_order(make_hansard):
    """Consensus → Split → Risks → Recommendation. Recommendation last."""
    md = render_markdown(make_hansard(), HansardLevel.VERDICT)
    positions = {
        "consensus":      md.index("> [!info] Consensus"),
        "split":          md.index("> [!warning] Split"),
        "risks":          md.index("> [!danger] Risks"),
        "recommendation": md.index("> [!success] Recommendation"),
    }
    assert positions["consensus"] < positions["split"]
    assert positions["split"] < positions["risks"]
    assert positions["risks"] < positions["recommendation"]


def test_verdict_callout_body_is_blockquoted(make_hansard):
    md = render_markdown(make_hansard(consensus="One.\nTwo."), HansardLevel.VERDICT)
    # Each line of body must be `> ` prefixed.
    assert "> One." in md
    assert "> Two." in md


def test_callout_bullet_list_lines_are_blockquoted(make_hansard):
    md = render_markdown(
        make_hansard(risks="- First risk\n- Second risk"),
        HansardLevel.VERDICT,
    )
    assert "> - First risk" in md
    assert "> - Second risk" in md
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
python -m pytest tests/test_render_markdown.py -v
```

Expected: all tests pass — Task 5's implementation already handles this correctly.

- [ ] **Step 3: Commit**

```bash
git add tests/test_render_markdown.py
git commit -m "test(hansard): lock verdict-level callout ordering and quoting"
```

---

## Task 7: `render_markdown` — empty section omission + recommendation fallback

**Files:**
- Modify: `tests/test_render_markdown.py`

(Source already supports this from Task 5; this task adds explicit edge-case tests.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_markdown.py`:

```python
def test_empty_split_section_is_omitted(make_hansard):
    md = render_markdown(make_hansard(split=""), HansardLevel.VERDICT)
    assert "[!warning] Split" not in md
    # Other sections still present
    assert "[!info] Consensus" in md
    assert "[!success] Recommendation" in md


def test_empty_consensus_and_risks_omitted(make_hansard):
    md = render_markdown(make_hansard(consensus="", risks=""), HansardLevel.VERDICT)
    assert "[!info] Consensus" not in md
    assert "[!danger] Risks" not in md
    assert "[!success] Recommendation" in md  # still present


def test_empty_recommendation_renders_placeholder(make_hansard):
    md = render_markdown(make_hansard(recommendation=""), HansardLevel.VERDICT)
    assert "> [!success] Recommendation" in md
    assert "(no recommendation parsed)" in md


def test_whitespace_only_section_treated_as_empty(make_hansard):
    md = render_markdown(make_hansard(split="   \n  \n"), HansardLevel.VERDICT)
    assert "[!warning] Split" not in md
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
python -m pytest tests/test_render_markdown.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_render_markdown.py
git commit -m "test(hansard): empty-section omission and recommendation placeholder"
```

---

## Task 8: `render_markdown` — archive level (frontmatter + footer)

**Files:**
- Modify: `src/parliament/render/hansard.py`
- Modify: `tests/test_render_markdown.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_markdown.py`:

```python
def test_archive_includes_yaml_frontmatter(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    lines = md.split("\n")
    assert lines[0] == "---"
    assert any(line.startswith("id: ") for line in lines[:10])
    assert any(line.startswith("created_at: ") for line in lines[:10])
    assert "type: parliament-hansard" in md
    assert any(line.startswith("speaker: ") for line in lines[:10])
    assert "members:" in md


def test_archive_frontmatter_lists_each_member(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    # Each of the three default members should appear under `members:`
    assert "Alpha (mock/mock-v1)" in md
    assert "Beta (mock/mock-v2)" in md
    assert "Gamma (mock/mock-v3)" in md


def test_archive_includes_session_footer(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    assert "## Session" in md
    assert "- Speaker: Alpha" in md
    assert "- Calls: 7" in md  # 3 members * 2 phases + 1 division
    assert "- Duration: 12.3s" in md  # from default duration_ms=12345


def test_archive_still_omits_transcripts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    assert "## First Reading" not in md
    assert "## Debate" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_render_markdown.py -v -k archive
```

Expected: 4 new archive tests fail (frontmatter and footer not yet rendered).

- [ ] **Step 3: Extend `render_markdown` with frontmatter and footer**

In `src/parliament/render/hansard.py`, replace the `render_markdown` function with this version:

```python
def render_markdown(hansard: "Hansard", level: HansardLevel) -> str:
    """Render a Hansard as Markdown with Obsidian/GitHub callouts.

    Verdict-block ordering inside the file: Consensus → Split → Risks →
    Recommendation (recommendation last). Empty sections are omitted for
    everything except recommendation, which is always rendered (with a
    placeholder if the Speaker's parser produced an empty string).
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

    if includes(level, "footer"):
        parts.append(_render_footer(hansard))

    return "\n".join(parts).rstrip() + "\n"


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_render_markdown.py -v
```

Expected: all tests pass (existing minimal/verdict + new archive).

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_render_markdown.py
git commit -m "feat(hansard): archive level adds frontmatter + session footer"
```

---

## Task 9: `render_markdown` — full level (transcripts)

**Files:**
- Modify: `src/parliament/render/hansard.py`
- Modify: `tests/test_render_markdown.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_markdown.py`:

```python
def test_full_includes_first_reading_section(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert "## First Reading" in md
    # Each member's heading + content
    assert "### Alpha" in md
    assert "First-reading content body. (Alpha)" in md
    assert "First-reading content body. (Beta)" in md
    assert "First-reading content body. (Gamma)" in md


def test_full_includes_debate_section(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert "## Debate" in md
    assert "### Alpha (critique)" in md
    assert "Debate critique content body. (Alpha)" in md


def test_full_includes_frontmatter_and_footer(make_hansard):
    """Full is a strict superset of archive."""
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert md.startswith("---\n")
    assert "## Session" in md


def test_full_transcripts_appear_after_verdict(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    rec_idx = md.index("> [!success] Recommendation")
    fr_idx = md.index("## First Reading")
    debate_idx = md.index("## Debate")
    assert rec_idx < fr_idx
    assert fr_idx < debate_idx
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_render_markdown.py -v -k full
```

Expected: 4 tests fail — transcripts not yet rendered.

- [ ] **Step 3: Extend `render_markdown` with transcript sections**

Modify `render_markdown` in `src/parliament/render/hansard.py` — insert the transcript blocks **between** the verdict callouts and the footer (so the footer remains the last block when present):

```python
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

    return "\n".join(parts).rstrip() + "\n"
```

- [ ] **Step 4: Run all markdown tests**

```bash
python -m pytest tests/test_render_markdown.py -v
```

Expected: all tests pass (minimal, verdict, archive, full).

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_render_markdown.py
git commit -m "feat(hansard): full level adds first-reading + debate transcripts"
```

---

## Task 10: `render_terminal` — minimal + verdict levels

**Files:**
- Modify: `src/parliament/render/hansard.py`
- Create: `tests/test_render_terminal.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render_terminal.py
"""Terminal rendering — Rich panels mirroring the markdown callouts."""

from __future__ import annotations

import io

from rich.console import Console

from parliament.render.hansard import HansardLevel, render_terminal


def _capture(level, hansard) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    render_terminal(hansard, level, console)
    return buf.getvalue()


def test_minimal_renders_question_panel_and_recommendation_only(make_hansard):
    out = _capture(HansardLevel.MINIMAL, make_hansard())
    assert "Should we use Postgres or MongoDB?" in out
    assert "✓ Recommendation" in out
    assert "Postgres. ACID" in out
    # No other verdict panels at minimal
    assert "ℹ Consensus" not in out
    assert "⚖ Split" not in out
    assert "! Risks" not in out


def test_verdict_renders_all_four_panels(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "ℹ Consensus" in out
    assert "⚖ Split" in out
    assert "! Risks" in out
    assert "✓ Recommendation" in out


def test_verdict_panels_in_canonical_order(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert out.index("ℹ Consensus") < out.index("⚖ Split")
    assert out.index("⚖ Split") < out.index("! Risks")
    assert out.index("! Risks") < out.index("✓ Recommendation")


def test_verdict_omits_transcripts_in_terminal(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "📖 First Reading" not in out
    assert "🗣 Debate" not in out


def test_empty_section_panel_omitted(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard(split=""))
    assert "⚖ Split" not in out


def test_empty_recommendation_renders_placeholder(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard(recommendation=""))
    assert "✓ Recommendation" in out
    assert "(no recommendation parsed)" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_render_terminal.py -x
```

Expected: ImportError on `render_terminal`.

- [ ] **Step 3: Implement `render_terminal`**

Append to `src/parliament/render/hansard.py`:

```python
from rich.console import Console
from rich.panel import Panel


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


def render_terminal(hansard: "Hansard", level: HansardLevel, console: Console) -> None:
    """Print a Hansard to a Rich console using callout-mirroring panels.

    Side-effect API: writes to `console`. The level governs which sections
    appear; section ordering matches `render_markdown`. Empty sections are
    omitted (recommendation excepted — placeholder fills in).
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_render_terminal.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_render_terminal.py
git commit -m "feat(hansard): render_terminal supports minimal + verdict levels"
```

---

## Task 11: `render_terminal` — full level (transcripts) + archive footer

**Files:**
- Modify: `src/parliament/render/hansard.py`
- Modify: `tests/test_render_terminal.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_terminal.py`:

```python
def test_full_renders_first_reading_panels(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert "📖 First Reading" in out
    # Each member's first-reading content
    assert "First-reading content body. (Alpha)" in out
    assert "First-reading content body. (Beta)" in out
    assert "First-reading content body. (Gamma)" in out


def test_full_renders_debate_panels(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert "🗣 Debate" in out
    assert "Alpha (critique)" in out
    assert "Debate critique content body. (Alpha)" in out


def test_full_transcripts_appear_after_verdict(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert out.index("✓ Recommendation") < out.index("📖 First Reading")
    assert out.index("📖 First Reading") < out.index("🗣 Debate")


def test_archive_renders_session_footer_in_terminal(make_hansard):
    out = _capture(HansardLevel.ARCHIVE, make_hansard())
    assert "Session: 12.3s" in out
    assert "Calls: 7" in out
    assert "Speaker: Alpha" in out


def test_verdict_does_not_render_session_footer(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "Session:" not in out
    assert "Calls:" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_render_terminal.py -v -k "full or archive or footer"
```

Expected: new tests fail.

- [ ] **Step 3: Extend `render_terminal` with transcript and footer rendering**

In `src/parliament/render/hansard.py`, replace `render_terminal` with the extended version:

```python
def render_terminal(hansard: "Hansard", level: HansardLevel, console: Console) -> None:
    """Print a Hansard to a Rich console using callout-mirroring panels.

    Side-effect API: writes to `console`. The level governs which sections
    appear; section ordering matches `render_markdown`. Empty sections are
    omitted (recommendation excepted — placeholder fills in).
    """
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


def _print_terminal_footer(hansard: "Hansard", console: Console) -> None:
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
```

- [ ] **Step 4: Run all terminal tests**

```bash
python -m pytest tests/test_render_terminal.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/parliament/render/hansard.py tests/test_render_terminal.py
git commit -m "feat(hansard): full-level transcripts + archive footer in terminal"
```

---

## Task 12: CLI — add `--hansard` flag + `--verbose` alias

**Files:**
- Modify: `src/parliament/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
# At top of file, near other markers:
_VERDICT_RECOMMENDATION_MARKER = "✓ Recommendation"
_FULL_TRANSCRIPT_MARKER = "📖 First Reading"


def test_ask_default_uses_verdict_level(monkeypatch):
    """Default behavior: post-run terminal shows verdict block, no transcripts."""
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    monkeypatch.delenv("PARLIAMENT_SHOW_DEBATE", raising=False)

    result = CliRunner().invoke(cli.main, ["ask", "--mock", "--no-show-debate", "Test?"])

    assert result.exit_code == 0, result.output
    # All four verdict panels appear; no transcripts.
    assert "ℹ Consensus" in result.output
    assert "⚖ Split" in result.output
    assert "! Risks" in result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert _FULL_TRANSCRIPT_MARKER not in result.output


def test_ask_minimal_level_omits_other_verdict_sections(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--hansard", "minimal", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert "ℹ Consensus" not in result.output
    assert "⚖ Split" not in result.output


def test_ask_full_level_shows_transcripts(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--hansard", "full", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _FULL_TRANSCRIPT_MARKER in result.output
    assert "🗣 Debate" in result.output


def test_verbose_flag_aliases_to_full(monkeypatch):
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main, ["ask", "--mock", "--no-show-debate", "--verbose", "Test?"]
    )
    assert result.exit_code == 0, result.output
    assert _FULL_TRANSCRIPT_MARKER in result.output


def test_explicit_hansard_flag_wins_over_verbose(monkeypatch):
    """When both --verbose and --hansard are passed, --hansard wins (more specific)."""
    monkeypatch.delenv("PARLIAMENT_HANSARD_LEVEL", raising=False)
    result = CliRunner().invoke(
        cli.main,
        ["ask", "--mock", "--no-show-debate", "--verbose", "--hansard", "verdict", "Test?"],
    )
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert _FULL_TRANSCRIPT_MARKER not in result.output


def test_env_var_sets_level(monkeypatch):
    monkeypatch.setenv("PARLIAMENT_HANSARD_LEVEL", "minimal")
    result = CliRunner().invoke(cli.main, ["ask", "--mock", "--no-show-debate", "Test?"])
    assert result.exit_code == 0, result.output
    assert _VERDICT_RECOMMENDATION_MARKER in result.output
    assert "ℹ Consensus" not in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_cli.py -v -k "hansard or verbose or default_uses"
```

Expected: new tests fail because the flag and renderer wiring don't exist yet.

- [ ] **Step 3: Wire `--hansard` into `cli.py`**

In `src/parliament/cli.py`, update imports:

```python
from parliament.config import (
    KEYS_FILE,
    KEY_PROVIDERS,
    build_parliament_from_config,
    load_config,
    load_keys,
    resolve_hansard_level,
    resolve_show_debate,
    save_key,
    remove_key,
)
from parliament.core.model_tiers import get_tier_label, detect_gap
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard
from parliament.render import build_renderer
from parliament.render.hansard import HansardLevel, render_terminal
```

In the `ask` command decorator stack, replace the existing `--verbose` and add `--hansard` so the option block becomes:

```python
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
def ask(
    question: str,
    config_path: Path | None,
    speaker: str | None,
    hansard_flag: str | None,
    verbose: bool,
    show_debate: bool | None,
    mock: bool,
):
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
        renderer = build_renderer(show_debate=show, mode="cli", console=console)

        p = Parliament(
            members=members,
            providers=providers,
            on_progress=renderer.emit,
            speaker_override=speaker,
        )

        for warning in p.check_gaps():
            console.print(f"[yellow]Warning: {warning}[/yellow]")

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
            if show:
                hansard = asyncio.run(p.ask(question))
            else:
                with console.status("[bold]First Reading...[/bold]"):
                    hansard = asyncio.run(p.ask(question))

        render_terminal(hansard, level, console)

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
```

Then **delete** `_render_synthesis` (lines ~53-86) and `_render_verbose` (lines ~89-99) from the file — they are now unused. Also remove the unused imports `Panel` and `Table` if no other call site uses them (the `Panel.fit` for the session header still uses Panel, so keep it; Table is no longer needed if `_render_synthesis` is gone — but `_configured_keys` and the `keys_list`/`members` commands also use `Table`, so leave `Table` imported).

- [ ] **Step 4: Run CLI tests**

```bash
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass (existing 10 + new 6 = 16).

- [ ] **Step 5: Run full suite to check for regressions**

```bash
python -m pytest -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/parliament/cli.py tests/test_cli.py
git commit -m "feat(cli): --hansard flag with --verbose alias for back-compat"
```

---

## Task 13: TUI / save_hansard signature — accept level

**Files:**
- Modify: `src/parliament/tui.py`
- Modify: `tests/test_tui.py` (rewrite `test_save_hansard_writes_markdown`)

- [ ] **Step 1: Write the failing test**

Replace `test_save_hansard_writes_markdown` in `tests/test_tui.py` with:

```python
def test_save_hansard_writes_verdict_level_by_default(make_hansard, tmp_path):
    """Without an explicit level, save_hansard defaults to VERDICT (compact)."""
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.VERDICT)

    text = path.read_text(encoding="utf-8")
    assert "# Should we use Postgres or MongoDB?" in text
    # All four callouts present at verdict level
    assert "> [!info] Consensus" in text
    assert "> [!warning] Split" in text
    assert "> [!danger] Risks" in text
    assert "> [!success] Recommendation" in text
    # No frontmatter, no transcripts
    assert not text.startswith("---")
    assert "## First Reading" not in text


def test_save_hansard_writes_full_level_with_transcripts(make_hansard, tmp_path):
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.FULL)

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")  # frontmatter
    assert "## First Reading" in text
    assert "## Debate" in text
    assert "## Session" in text


def test_save_hansard_filename_includes_slug_and_id_prefix(make_hansard, tmp_path):
    from parliament.render.hansard import HansardLevel

    hansard = make_hansard()
    path = save_hansard(hansard, str(tmp_path), level=HansardLevel.VERDICT)

    name = path.name
    # Format: YYYYMMDD-HHMMSS-slug-shortid.md
    assert name.endswith(".md")
    assert hansard.id[:8] in name
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tui.py::test_save_hansard_writes_verdict_level_by_default -v
```

Expected: TypeError ("`save_hansard()` got an unexpected keyword argument 'level'") or similar.

- [ ] **Step 3: Update `save_hansard` in `tui.py`**

Replace `save_hansard` and delete `_hansard_markdown` in `src/parliament/tui.py`. Find the existing `save_hansard` and `_hansard_markdown` functions and replace them with:

```python
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
```

Then **delete** the entire `_hansard_markdown` function (~50 lines starting `def _hansard_markdown(hansard: Hansard) -> str:`). It is replaced by `parliament.render.hansard.render_markdown`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tui.py -v -k save_hansard
```

Expected: 3 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/parliament/tui.py tests/test_tui.py
git commit -m "refactor(tui): save_hansard uses render_markdown; level kwarg added"
```

---

## Task 14: TUI / `_run_debate` — pass level to save_hansard

**Files:**
- Modify: `src/parliament/tui.py`

- [ ] **Step 1: Find current callers of `save_hansard`**

```bash
grep -n "save_hansard(" src/parliament/tui.py
```

There should be two callsites: the auto-save in the result screen (post-debate) and the `s`-key retry on the result screen.

- [ ] **Step 2: Resolve level once after the debate, pass to both saves**

In `_run_debate` (or the surrounding `_run` loop where `hansard` becomes available), call `resolve_hansard_level(cli_flag=None, config=config)` and store in a local variable. Pass that to both `save_hansard` calls.

Concrete edit: just before each `save_hansard(hansard, app_settings.save_dir)` call, change to `save_hansard(hansard, app_settings.save_dir, level=resolved_level)`. Add `resolved_level = resolve_hansard_level(cli_flag=None, config=config)` to `_run`'s state setup near where other helpers are resolved.

Add the import at the top of `tui.py`:

```python
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
```

- [ ] **Step 3: Run TUI tests + full suite**

```bash
python -m pytest -q
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/parliament/tui.py
git commit -m "feat(tui): _run_debate threads hansard level into save_hansard"
```

---

## Task 15: TUI Settings — extend `SettingsScreenState` with `hansard_level`

**Files:**
- Modify: `src/parliament/tui.py`
- Modify: `tests/test_tui_settings_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui_settings_screen.py`:

```python
def test_settings_state_includes_hansard_level():
    from parliament.render.hansard import HansardLevel
    state = tui_mod._init_settings_state(save_dir="/tmp/x", config={})
    assert state.hansard_level is HansardLevel.VERDICT  # default


def test_settings_state_loads_hansard_level_from_config():
    from parliament.render.hansard import HansardLevel
    state = tui_mod._init_settings_state(
        save_dir="/tmp/x",
        config={"hansard": {"level": "archive"}},
    )
    assert state.hansard_level is HansardLevel.ARCHIVE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tui_settings_screen.py -v -k hansard_level
```

Expected: AttributeError on `hansard_level`.

- [ ] **Step 3: Extend `SettingsScreenState` and `_init_settings_state`**

In `src/parliament/tui.py`, replace the existing `SettingsScreenState` and `_init_settings_state` with:

```python
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


def _init_settings_state(save_dir: str, config: dict[str, Any]) -> SettingsScreenState:
    """Build the initial Settings-screen state from persisted sources."""
    from parliament.render.hansard import HansardLevel

    show_debate = bool(config.get("display", {}).get("show_debate", True))
    raw_level = (config.get("hansard") or {}).get("level")
    hansard_level = HansardLevel.parse(raw_level)
    return SettingsScreenState(
        save_dir=save_dir,
        show_debate=show_debate,
        hansard_level=hansard_level,
        focus="save_dir",
    )
```

Add the `HansardLevel` import to `tui.py` if not already present (it is needed at type-check time for the dataclass annotation):

```python
from parliament.render.hansard import HansardLevel
```

(Place near the existing `from parliament.render import build_renderer` import line.)

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tui_settings_screen.py -v
```

Expected: all tests pass (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/parliament/tui.py tests/test_tui_settings_screen.py
git commit -m "feat(tui): SettingsScreenState gains hansard_level field"
```

---

## Task 16: TUI Settings — cycle widget key handling

**Files:**
- Modify: `src/parliament/tui.py` (extend `_handle_settings_key`)
- Modify: `tests/test_tui_settings_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui_settings_screen.py`:

```python
def test_tab_cycles_through_three_fields():
    s1 = _state(focus="save_dir")
    s2, _ = _handle_settings_key(s1, 9)
    assert s2.focus == "hansard_level"
    s3, _ = _handle_settings_key(s2, 9)
    assert s3.focus == "show_debate"
    s4, _ = _handle_settings_key(s3, 9)
    assert s4.focus == "save_dir"


def test_right_arrow_cycles_hansard_level_forward():
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")  # default level=VERDICT
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.ARCHIVE
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.FULL
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.MINIMAL  # wraps


def test_left_arrow_cycles_hansard_level_backward():
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")
    s, _ = _handle_settings_key(s, curses.KEY_LEFT)
    assert s.hansard_level is HansardLevel.MINIMAL  # wraps from VERDICT


def test_space_on_hansard_field_cycles_forward():
    """Space behaves the same as right arrow when the level field is focused."""
    from parliament.render.hansard import HansardLevel
    s = _state(focus="hansard_level")
    s, _ = _handle_settings_key(s, ord(" "))
    assert s.hansard_level is HansardLevel.ARCHIVE


def test_arrows_on_save_dir_field_dont_cycle_level():
    """Left/Right arrows on save_dir should be a no-op (text fields don't cycle)."""
    from parliament.render.hansard import HansardLevel
    s = _state(focus="save_dir")  # default level=VERDICT
    s, _ = _handle_settings_key(s, curses.KEY_RIGHT)
    assert s.hansard_level is HansardLevel.VERDICT  # unchanged
    assert s.focus == "save_dir"
```

Update the local `_state` helper in `tests/test_tui_settings_screen.py` so it now accepts the new field:

```python
def _state(save_dir="x", show_debate=True, hansard_level=None, focus="save_dir") -> SettingsScreenState:
    from parliament.render.hansard import HansardLevel
    if hansard_level is None:
        hansard_level = HansardLevel.VERDICT
    return SettingsScreenState(
        save_dir=save_dir,
        show_debate=show_debate,
        hansard_level=hansard_level,
        focus=focus,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tui_settings_screen.py -v -k "cycle or arrow or space"
```

Expected: new tests fail.

- [ ] **Step 3: Extend `_handle_settings_key`**

In `src/parliament/tui.py`, replace `_handle_settings_key` with:

```python
_HANSARD_LEVEL_CYCLE = (
    HansardLevel.MINIMAL,
    HansardLevel.VERDICT,
    HansardLevel.ARCHIVE,
    HansardLevel.FULL,
)


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


def _cycle_hansard_level(current: HansardLevel, direction: int) -> HansardLevel:
    """Advance through the level cycle by `direction` (±1) with wrap-around."""
    idx = _HANSARD_LEVEL_CYCLE.index(current)
    return _HANSARD_LEVEL_CYCLE[(idx + direction) % len(_HANSARD_LEVEL_CYCLE)]
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tui_settings_screen.py -v
```

Expected: all tests pass (cycle + existing).

- [ ] **Step 5: Commit**

```bash
git add src/parliament/tui.py tests/test_tui_settings_screen.py
git commit -m "feat(tui): cycle widget key handling for hansard_level field"
```

---

## Task 17: TUI Settings — rename `_save_show_debate` → `_save_settings`, persist level

**Files:**
- Modify: `src/parliament/tui.py`
- Modify: `tests/test_tui_settings_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui_settings_screen.py`:

```python
def test_save_settings_writes_both_show_debate_and_hansard_level(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {"parliament": {"name": "X", "members": []}, "providers": {}}
    _write_yaml(cfg_path, runtime)

    from parliament.render.hansard import HansardLevel
    from parliament.tui import _save_settings

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.ARCHIVE,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "archive"
    # Runtime config also updated
    assert runtime["display"]["show_debate"] is False
    assert runtime["hansard"]["level"] == "archive"


def test_save_settings_mock_mode_does_not_write_disk(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    runtime = {"parliament": {"name": "Mock", "members": []}, "providers": {}}

    from parliament.render.hansard import HansardLevel
    from parliament.tui import _save_settings

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.MINIMAL,
        persist=False,
    )

    assert not cfg_path.exists()
    assert runtime["display"]["show_debate"] is False
    assert runtime["hansard"]["level"] == "minimal"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tui_settings_screen.py -v -k save_settings
```

Expected: ImportError on `_save_settings`.

- [ ] **Step 3: Replace `_save_show_debate` with `_save_settings`**

In `src/parliament/tui.py`, **replace** `_save_show_debate` with:

```python
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
```

Then update the call site (the `screen == "app_settings"` action handler) to use the new function. Find:

```python
config = _save_show_debate(
    config,
    active_config_path,
    settings_state.show_debate,
    persist=not mock,
)
```

Replace with:

```python
config = _save_settings(
    config,
    active_config_path,
    show_debate=settings_state.show_debate,
    hansard_level=settings_state.hansard_level,
    persist=not mock,
)
```

Update the message that prints after save (currently mentions only the live view label) to also mention the level:

```python
live_label = "live view ON" if settings_state.show_debate else "live view OFF"
level_label = settings_state.hansard_level.value
if mock:
    message = f"Settings updated for this session ({live_label} · level: {level_label}; mock mode — not saved)."
else:
    message = f"Settings saved ({live_label} · level: {level_label}, save dir: {app_settings.save_dir})."
```

- [ ] **Step 4: Update existing `_save_show_debate` tests**

Find any test in `tests/test_tui_settings_screen.py` that imports or asserts on `_save_show_debate`. Replace with `_save_settings` and pass the new keyword arguments. (Specifically, the existing tests `test_save_show_debate_writes_to_yaml_when_persist`, `test_save_show_debate_preserves_other_keys`, `test_save_show_debate_mock_mode_does_not_write_disk`, and `test_save_show_debate_overwrites_existing_value` need updates: change the import to `_save_settings`, and change the call to pass `show_debate=...` and `hansard_level=HansardLevel.VERDICT` as keyword arguments. The assertions on `display.show_debate` stay; add an assertion that `hansard.level` is also present in those that go through `persist=True`.)

Concretely, replace each of those four existing tests with this updated version:

```python
def test_save_settings_writes_to_yaml_when_persist(tmp_path):
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _save_settings

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.VERDICT,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "verdict"
    assert runtime["display"]["show_debate"] is False


def test_save_settings_preserves_other_keys(tmp_path):
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _save_settings

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {
            "name": "House of AI",
            "members": [{"name": "A", "provider": "mock", "model": "mock-v1"}],
        },
        "providers": {"ollama": {"base_url": "http://localhost:11434/v1"}},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=True,
        hansard_level=HansardLevel.FULL,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["parliament"]["name"] == "House of AI"
    assert on_disk["parliament"]["members"][0]["name"] == "A"
    assert on_disk["providers"]["ollama"]["base_url"] == "http://localhost:11434/v1"
    assert on_disk["display"]["show_debate"] is True
    assert on_disk["hansard"]["level"] == "full"


def test_save_settings_overwrites_existing_values(tmp_path):
    from parliament.render.hansard import HansardLevel
    from parliament.tui import _save_settings

    cfg_path = tmp_path / "config.yaml"
    runtime = {
        "parliament": {"name": "X", "members": []},
        "providers": {},
        "display": {"show_debate": True},
        "hansard": {"level": "minimal"},
    }
    _write_yaml(cfg_path, runtime)

    _save_settings(
        runtime,
        cfg_path,
        show_debate=False,
        hansard_level=HansardLevel.ARCHIVE,
        persist=True,
    )

    on_disk = _read_yaml(cfg_path)
    assert on_disk["display"]["show_debate"] is False
    assert on_disk["hansard"]["level"] == "archive"
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_tui_settings_screen.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/parliament/tui.py tests/test_tui_settings_screen.py
git commit -m "refactor(tui): rename _save_show_debate to _save_settings; persist hansard.level"
```

---

## Task 18: TUI Settings — `_draw_app_settings` cycle widget rendering

**Files:**
- Modify: `src/parliament/tui.py`
- Modify: `tests/test_tui_settings_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui_settings_screen.py`:

```python
def test_settings_screen_renders_hansard_level_cycle(make_hansard=None):
    """Settings screen draws the level cycle widget with current bracketed."""
    from parliament.render.hansard import HansardLevel
    scr = _FakeStdscr()
    state = _state(hansard_level=HansardLevel.VERDICT, focus="hansard_level")
    _draw_app_settings(scr, state, 24, 80)
    body = scr.text()
    # All four levels appear inline; current is bracketed.
    assert "minimal" in body
    assert "[verdict]" in body
    assert "archive" in body
    assert "full" in body


def test_settings_screen_focus_highlights_hansard_level_row():
    from parliament.render.hansard import HansardLevel
    scr = _FakeStdscr()
    _draw_app_settings(
        scr,
        _state(hansard_level=HansardLevel.VERDICT, focus="hansard_level"),
        24,
        80,
    )
    by_y = {y: attr for y, _, _, attr in scr.lines}
    # The level value row is reversed when focused; save_dir row is not.
    # (Find the y position by looking for the bracketed level token.)
    level_row_y = next(
        y for y, _, t, _ in scr.lines if "[verdict]" in t
    )
    assert by_y[level_row_y] & curses.A_REVERSE


def test_settings_screen_renders_each_level_bracketed_in_turn():
    from parliament.render.hansard import HansardLevel
    for lvl in (HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL):
        scr = _FakeStdscr()
        _draw_app_settings(scr, _state(hansard_level=lvl), 24, 80)
        body = scr.text()
        assert f"[{lvl.value}]" in body
        # Other three levels appear without brackets
        for other in (HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL):
            if other is lvl:
                continue
            assert f"[{other.value}]" not in body
            assert other.value in body  # but the bare name still appears
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tui_settings_screen.py -v -k "cycle or hansard_level_row"
```

Expected: tests fail because `_draw_app_settings` doesn't render the level field.

- [ ] **Step 3: Update `_draw_app_settings`**

In `src/parliament/tui.py`, replace `_draw_app_settings` with the three-field version. The Settings screen layout becomes (in order):

1. Title row
2. Footer hint row (1 line below title)
3. Save directory label + value row
4. Hansard detail level label + cycle widget + sublabel
5. Live debate view label + checkbox + sublabel
6. Bottom hint at `height - 2`

```python
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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tui_settings_screen.py -v
```

Expected: all tests pass. NB: the existing `test_settings_screen_focus_highlights_save_dir_row` and `test_settings_screen_focus_highlights_toggle_row` tests reference `y=4` and `y=7`. Update those tests to use the new row positions: save_dir is still y=4, the toggle row moved from y=7 to y=11. Find:

```python
def test_settings_screen_focus_highlights_save_dir_row():
    ...
    assert by_y[4] & curses.A_REVERSE
    assert not (by_y[7] & curses.A_REVERSE)


def test_settings_screen_focus_highlights_toggle_row():
    ...
    assert by_y[7] & curses.A_REVERSE
    assert not (by_y[4] & curses.A_REVERSE)
```

Replace with:

```python
def test_settings_screen_focus_highlights_save_dir_row():
    """When focus=save_dir, the save_dir value row (y=4) is reversed; other field rows are not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="save_dir"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[4] & curses.A_REVERSE
    assert not (by_y[7] & curses.A_REVERSE)   # hansard_level row
    assert not (by_y[11] & curses.A_REVERSE)  # show_debate row


def test_settings_screen_focus_highlights_toggle_row():
    """When focus=show_debate, the toggle row (y=11) is reversed; others not."""
    scr = _FakeStdscr()
    _draw_app_settings(scr, _state(save_dir="/tmp/h", focus="show_debate"), 24, 80)
    by_y = {y: attr for y, _, _, attr in scr.lines}
    assert by_y[11] & curses.A_REVERSE
    assert not (by_y[4] & curses.A_REVERSE)
    assert not (by_y[7] & curses.A_REVERSE)
```

- [ ] **Step 5: Run all tests + lint**

```bash
python -m pytest -q
ruff check .
```

Expected: all green, lint clean.

- [ ] **Step 6: Commit**

```bash
git add src/parliament/tui.py tests/test_tui_settings_screen.py
git commit -m "feat(tui): Settings screen renders hansard_level cycle widget"
```

---

## Task 19: Example configs — add `hansard:` block

**Files:**
- Modify: `config.example.yaml`
- Modify: `config.cloud.yaml`
- Modify: `config.mixed.yaml`

- [ ] **Step 1: Update `config.example.yaml`**

Append after the existing `display:` block:

```yaml

# Hansard detail level — controls saved .md file and post-run terminal print.
# Override per-call with --hansard or PARLIAMENT_HANSARD_LEVEL.
#   minimal  recommendation only
#   verdict  full synthesis (default)
#   archive  + frontmatter + session footer
#   full     + first-reading and debate transcripts
hansard:
  level: verdict
```

- [ ] **Step 2: Update `config.cloud.yaml`**

Append the same block after the existing `display:` block.

- [ ] **Step 3: Update `config.mixed.yaml`**

Append the same block after the existing `display:` block.

- [ ] **Step 4: Verify the bundled example still loads cleanly**

Run the existing config-test that reads `config.example.yaml`:

```bash
python -m pytest tests/test_config.py -v
```

Expected: existing tests pass; the new `hansard:` block is silently round-tripped.

- [ ] **Step 5: Add a test asserting `level: verdict` round-trips through the example config**

Append to `tests/test_config.py`:

```python
def test_example_config_carries_hansard_level(fresh_home):
    """The bundled example must surface hansard.level so users discover the toggle."""
    config, _ = fresh_home
    cfg = config.load_config()
    assert cfg.get("hansard", {}).get("level") == "verdict"
```

- [ ] **Step 6: Run config tests**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add config.example.yaml config.cloud.yaml config.mixed.yaml tests/test_config.py
git commit -m "docs(config): add hansard.level block to example configs"
```

---

## Task 20: README — Hansard detail levels section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find the right insertion point**

Open `README.md` and locate the `### Live debate view` subsection under `## CLI Usage`. Insert the new section immediately **after** the live-debate subsection ends (before the `TUI controls:` block).

- [ ] **Step 2: Add the new subsection**

```markdown
### Hansard detail levels

By default, both the post-run terminal output and the saved `.md` file
contain the four-part Speaker synthesis (Consensus, Split, Risks,
Recommendation) — no LLM transcripts. Older runs that included the full
debate text by default are now opt-in via `--hansard=full`.

Four levels:

| Level | Includes | Roughly |
|---|---|---|
| `minimal` | Recommendation only | one paragraph — "just tell me what to do" |
| `verdict` | Full four-part synthesis | **default** — concise but complete |
| `archive` | + YAML frontmatter + session footer | searchable in Obsidian, no walls of text |
| `full` | + First Reading + Debate transcripts | today's full record (≈ what `--verbose` used to print) |

Set the level via three precedence-ordered sources:

| Precedence | Source | Example |
| --- | --- | --- |
| 1 (highest) | CLI flag | `parliament ask "..." --hansard archive` |
| 2 | Environment variable | `PARLIAMENT_HANSARD_LEVEL=full parliament ask "..."` |
| 3 | YAML config | `hansard:\n  level: archive` |
| 4 (default) | Built-in | `verdict` |

`--verbose` continues to work; it's an alias for `--hansard=full`.
The level applies to the saved `.md` file **and** the post-run terminal
output. The live in-flight debate view is independent — toggle it
separately with `--show-debate` / `--no-show-debate`.
```

- [ ] **Step 3: Sanity-check the markdown**

```bash
grep -n "Hansard detail levels" README.md
```

Expected: prints the new subsection heading.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): document Hansard detail levels and override paths"
```

---

## Task 21: RELEASING.md — note behavior change

**Files:**
- Modify: `RELEASING.md`

- [ ] **Step 1: Add a "Notable changes" entry under the next-release notes section**

Open `RELEASING.md`. Find an appropriate section for tracking unreleased changes (or add one if not present). Append:

```markdown
### Behavior change: compact Hansards by default

The post-run terminal output and saved `.md` file now contain only the
four-part Speaker synthesis at the new default detail level (`verdict`).
Previously, the saved file always included the full First Reading and
Debate transcripts; now those appear only at `--hansard=full` (or
`--verbose`, which aliases to full). This is an intentional UX shift
toward a smaller, more skimmable artifact.

Migration notes for existing users:

- Pass `--hansard=full` (or `--verbose`) to restore the previous
  chatty output.
- Set `hansard:\n  level: full` in `~/.parliament/config.yaml` to make
  full output the default again.
- Existing saved `.md` files are untouched — only new writes use the new
  format.

Three new control surfaces, all mirroring the recent `show_debate` toggle:
CLI flag `--hansard {minimal,verdict,archive,full}`, environment variable
`PARLIAMENT_HANSARD_LEVEL`, and config key `hansard.level`. Settable from
the TUI Settings screen as a fourth-state cycle widget.
```

- [ ] **Step 2: Commit**

```bash
git add RELEASING.md
git commit -m "docs(releasing): note hansard-redesign behavior change"
```

---

## Task 22: Final sweep — full suite, lint, smoke test

**Files:** none (verification step)

- [ ] **Step 1: Run the full test suite**

```bash
source .venv/bin/activate && python -m pytest -q
```

Expected: all tests pass (≈ 213 + ~60 new = ≈ 273).

- [ ] **Step 2: Lint**

```bash
ruff check .
```

Expected: clean.

- [ ] **Step 3: Smoke test against mock providers — verdict level (default)**

```bash
parliament ask --mock --no-show-debate "smoke verdict"
```

Expected output (after the session-header panel): four Rich panels in order — `ℹ Consensus`, `⚖ Split`, `! Risks`, `✓ Recommendation`. No `📖 First Reading` rule. No transcripts. No dim summary table at the bottom.

- [ ] **Step 4: Smoke test — minimal level**

```bash
parliament ask --mock --no-show-debate --hansard minimal "smoke minimal"
```

Expected: question panel + `✓ Recommendation` panel only.

- [ ] **Step 5: Smoke test — full level (back-compat with --verbose)**

```bash
parliament ask --mock --no-show-debate --verbose "smoke verbose"
parliament ask --mock --no-show-debate --hansard full "smoke full"
```

Expected (both): four verdict panels + `📖 First Reading` rule + 3 first-reading panels + `🗣 Debate` rule + 3 critique panels + summary table at bottom.

- [ ] **Step 6: Smoke test — saved markdown content**

```bash
ls -t ~/.parliament/hansards/ | head -3
cat ~/.parliament/hansards/$(ls -t ~/.parliament/hansards/ | head -1)
```

Expected: most recent file is verdict-level format — `# {question}` heading + four `> [!type]` callouts + nothing else. (Earlier smoke runs at `minimal` and `full` levels also wrote files; verify the most-recent matches the level used in step 5.)

- [ ] **Step 7: TUI smoke (manual, in your terminal — not from here)**

```bash
parliament --mock
# Press 's' to open Settings.
# Tab through the three fields: save_dir → hansard_level → show_debate.
# Cycle hansard_level with ←/→ arrows: minimal · [verdict] · archive · full.
# Press Enter to save.
# Confirm the message line shows "level: <chosen-level>".
# Run a debate. Confirm the saved .md uses the chosen level.
```

- [ ] **Step 8: Commit (if any pending changes from documentation tweaks)**

```bash
git status
# If clean, no commit needed. If small docs tweaks landed during smoke testing,
# commit them here with a clear message.
```

---

## Self-Review Checklist (verify before handoff)

| Spec section | Plan task(s) covering it |
|---|---|
| §3 Levels — minimal | Task 5 |
| §3 Levels — verdict | Tasks 5, 6 |
| §3 Levels — archive | Task 8 |
| §3 Levels — full | Task 9 |
| §3 Sections — empty omission | Task 7 |
| §3 Sections — recommendation always rendered | Task 7 |
| §4 CLI flag | Task 12 |
| §4 Env var | Task 3 (resolver) + Task 12 (CLI integration) |
| §4 Config key | Task 3 (resolver) + Task 19 (example configs) |
| §4 Precedence chain | Task 3 |
| §4 TUI Settings screen | Tasks 15, 16, 17, 18 |
| §4 TUI Settings persistence | Task 17 |
| §5 Markdown callouts | Tasks 5, 6, 8 |
| §5 Rich panel mirror | Tasks 10, 11 |
| §5 Question H1 every level | Tasks 5, 8, 9 |
| §5 Empty section omission | Tasks 7, 10 |
| §5 Recommendation never empty | Tasks 7, 10 |
| §6 New module placement | Tasks 1, 2, 5, 8, 9, 10, 11 |
| §6 Refactor existing code | Tasks 12 (cli), 13 (save_hansard), 14 (TUI run_debate), 17 (rename), 18 (settings draw) |
| §7 Test plan — `tests/test_hansard_level.py` | Tasks 1, 2 |
| §7 Test plan — `tests/test_resolve_hansard_level.py` | Task 3 |
| §7 Test plan — `tests/test_render_markdown.py` | Tasks 5, 6, 7, 8, 9 |
| §7 Test plan — `tests/test_render_terminal.py` | Tasks 10, 11 |
| §7 Test plan — extend `test_cli.py` | Task 12 |
| §7 Test plan — extend `test_tui_settings_screen.py` | Tasks 15, 16, 17, 18 |
| §7 Risk: rewrite `test_save_hansard_writes_markdown` | Task 13 |
| §7 Shared `make_hansard` fixture | Task 4 |
| §8 Migration: example configs | Task 19 |
| §8 Migration: README | Task 20 |
| §8 Migration: RELEASING.md | Task 21 |
| §10 Out of scope (live view restyling) | Not implemented (correct) |
| §11 Risk: TUI cycle widget | Tasks 16, 18 |

**No gaps.** Every spec section maps to at least one task. Tasks 4 (fixture) and 22 (final sweep) are infrastructure, not spec sections.

**No placeholders.** Searched for "TBD", "TODO", "implement later", "fill in details", and "Similar to Task N" — none present in the plan body.

**Type consistency.** All references to types and functions used in later tasks (`HansardLevel`, `includes`, `render_markdown`, `render_terminal`, `resolve_hansard_level`, `_save_settings`, `SettingsScreenState.hansard_level`, `_HANSARD_LEVEL_CYCLE`, `_cycle_hansard_level`) are defined in earlier tasks. Method signatures match across tasks.

---

## Execution Notes for the implementer

- The plan is sized for **one focused day** of TDD work. Each task = one commit; ~22 commits total.
- Run `python -m pytest -q && ruff check .` at the end of each task. If either fails, fix before committing.
- Commit messages use Conventional Commits style consistent with this repo's history (`feat:`, `feat(scope):`, `refactor:`, `docs:`, `test:`).
- Tasks 5–9 are sequential within `render_markdown`; do not skip ahead. Tasks 10–11 are sequential within `render_terminal`.
- Tasks 15–18 are sequential within the TUI Settings screen; the dataclass shape and the cycle constant must exist before later tasks reference them.
- Tasks 19–21 (configs + docs) can be reordered freely; they don't depend on each other.
