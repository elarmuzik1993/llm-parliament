# Design: Hansard Redesign — Levels & Callouts

**Status:** Approved (brainstorm), pending implementation plan
**Date:** 2026-05-09
**Author:** Boris (with Claude assist)
**Brainstorm session:** `.superpowers/brainstorm/188867-1778253843/`

## 1. Context

Today, every saved Hansard at `~/.parliament/hansards/...md` and every post-run terminal print is **maximalist**: full YAML frontmatter, the full four-part Speaker synthesis, two complete walls of text per member (First Reading + Debate critique), and a session-metadata footer. A typical 3-member debate produces ~30 KB of markdown, much of it the LLMs' verbatim prose. Boris reports the artifact feels "too massive and confusing" — he glances at the verdict, never reopens the file, and the rest is mostly noise.

There is no way to ask for a shorter artifact. The only existing knob, `--verbose`, controls whether the post-run *terminal* prints the transcript; it has no effect on what gets saved.

The user-stated requirement: **"keep simple as possible mostly like just verdict, but everything else modular and preference-choosable. Should be as simple as possible by default."** Existing power users (myself and anyone using `--verbose` daily) must keep working without change.

This spec redesigns the Hansard rendering layer to honor that: a four-level detail system with a compact default, callout-styled output, and the same precedence chain (CLI > env > config > default) used by the recent `show_debate` toggle.

## 2. Locked anchors (from brainstorm)

| # | Anchor | Decision |
|---|---|---|
| 1 | What goes in the smallest level | Recommendation only |
| 2 | What goes in the default level | Full four-part verdict block (Consensus + Split + Risks + Recommendation), no transcripts, no frontmatter, no footer |
| 3 | Control model | Four discrete levels — `minimal` / `verdict` / `archive` / `full` |
| 4 | Scope of the level | Saved `.md` file **and** post-run terminal output. Live in-flight view stays separate, governed by `show_debate` (already shipped). |
| 5 | Visual style | Obsidian/GitHub callouts in the `.md`; Rich panels mirroring the same colors in terminal |
| 6 | Approach | **B** — rendering layer + TUI Settings integration. Live spinner/panels untouched. |
| 7 | `--verbose` | Aliased to `--hansard=full` for back-compat. Not removed. |
| 8 | Verdict ordering | Consensus → Split → Risks → **Recommendation last**. Reads like a parliamentary record: deliberate first, conclude last. |

## 3. Levels

The four levels are strictly **monotonic** — each level's content set is a superset of the level below. Adding a fifth level later means adding one row to the section-inclusion matrix; no other changes.

| Level | Sections included |
|---|---|
| `minimal` | Question (`# H1`), Recommendation |
| `verdict` *(default)* | Question, Consensus, Split, Risks, Recommendation |
| `archive` | YAML frontmatter, Question, Consensus, Split, Risks, Recommendation, session footer |
| `full` | YAML frontmatter, Question, Consensus, Split, Risks, Recommendation, session footer, First Reading transcripts, Debate transcripts |

### Section semantics

- **YAML frontmatter** — `id`, `created_at`, `type: parliament-hansard`, `members: [...]`, `speaker`. Renders invisibly in most viewers; powers Obsidian Dataview and search.
- **Question** — the user's question rendered as `# H1`. Full text, no truncation. (Filename slug still gets truncated to 60 chars because filesystem.)
- **Consensus / Split / Risks / Recommendation** — the four fields parsed from the Speaker's synthesis. Each rendered as a callout (see §5). Empty sections are **omitted** for everything except Recommendation, which is always rendered (even if oddly short).
- **Session footer** — speaker name, member roster, total wall-clock duration, total LLM call count.
- **First Reading transcripts** — `## First Reading` heading, then `### {member name}` + content for each member.
- **Debate transcripts** — `## Debate` heading, then `### {member name} (critique)` + content for each member.

## 4. Public surface

### CLI flag

```bash
parliament ask "..." --hansard minimal      # just the recommendation
parliament ask "..." --hansard verdict      # default — full verdict block
parliament ask "..." --hansard archive      # + frontmatter + footer
parliament ask "..." --hansard full         # + transcripts (= today's --verbose)
parliament ask "..." --verbose              # alias for --hansard=full
```

`--verbose` stays. If both `--verbose` and `--hansard` are passed and disagree, `--hansard` wins (more specific).

### Environment variable

```bash
PARLIAMENT_HANSARD_LEVEL=archive parliament ask "..."
```

Same shape as `PARLIAMENT_SHOW_DEBATE`. Case-insensitive. Invalid values fall back to default with a warning printed to stderr.

### Config key

```yaml
# ~/.parliament/config.yaml
hansard:
  level: verdict     # one of: minimal, verdict, archive, full
```

Empty / missing → defaults to `verdict`. Mirrors the `display:\n  show_debate: true` shape exactly.

### Precedence resolver

```python
# src/parliament/config.py — sibling of resolve_show_debate
def resolve_hansard_level(*, cli_flag: str | None, config: dict) -> HansardLevel:
    if cli_flag is not None:
        return HansardLevel.parse(cli_flag)
    env = os.environ.get("PARLIAMENT_HANSARD_LEVEL")
    if env is not None:
        return HansardLevel.parse(env)
    raw = (config.get("hansard") or {}).get("level")
    return HansardLevel.parse(raw)
```

Order: **CLI flag > env > config > default `verdict`**. Identical to `resolve_show_debate`.

### TUI Settings screen

Settings screen gains a third focusable field, between save_dir and show_debate:

```
Settings
Enter: save  Tab: switch  Space: toggle  ←/→: cycle  b/Esc: cancel

Hansard save directory
 /home/boris/.parliament/hansards

Hansard detail level
 < minimal · [verdict] · archive · full >
   Just verdict / + frontmatter+footer / + transcripts

Live debate view
 [x] Show debate as it happens
     Also: --show-debate / --no-show-debate or PARLIAMENT_SHOW_DEBATE
```

**Cycle widget:** all four levels rendered inline; the current selection is `[bracketed]`. Tab/Down/Up move between fields as before; Left/Right (or Space) cycle through levels when this field is focused.

On Enter, the screen persists `display.show_debate` AND `hansard.level` to the YAML config (skipped in mock mode), via the same `_load_editable_config` + `save_config` round-trip used today. The legacy `_save_show_debate` helper is renamed to `_save_settings(runtime_config, config_path, *, show_debate, hansard_level, persist)`.

## 5. Visual rendering

### Saved markdown

Obsidian/GitHub callouts. Renders natively in both. In plain editors and non-supporting viewers, the source falls back to readable blockquotes — no information lost.

| Section | Callout type | Title |
|---|---|---|
| Consensus | `[!info]` | `Consensus` |
| Split | `[!warning]` | `Split` |
| Risks | `[!danger]` | `Risks` |
| Recommendation | `[!success]` | `Recommendation` |

**Sample — `verdict` level:**

```markdown
# Should we use Postgres or MongoDB?

> [!info] Consensus
> All three models agree relational structure fits a small SaaS better
> than document storage.

> [!warning] Split
> Disagreement on whether to plan for sharding now or defer until
> traffic warrants it.

> [!danger] Risks
> - Schema migration overhead as the product evolves
> - Read scaling under sustained load

> [!success] Recommendation
> Postgres. ACID guarantees, JSON columns when you need flex, and the
> ecosystem maturity outweighs MongoDB's edge for a small SaaS scaling
> on relational queries.
```

**Body formatting inside callouts:**
- Single paragraph → one quoted block.
- Multi-paragraph → blank `>` line between paragraphs.
- Lists → `> -` bullets.
- Multi-line content correctly prefixes every line (including blank separators) with `> `.

### Post-run terminal (Rich panels)

Rich doesn't render markdown callouts natively. The post-run terminal print uses Rich `Panel` widgets with border styles matching the callout palette and titles including a small icon for visual identity.

| Section | `border_style` | Title |
|---|---|---|
| Consensus | `blue` | `ℹ Consensus` |
| Split | `yellow` | `⚖ Split` |
| Risks | `red` | `! Risks` |
| Recommendation | `bold green` | `✓ Recommendation` |

Recommendation gets `bold green` (slightly heavier weight) because it's the deliverable.

The question is rendered as a compact `Panel.fit(...)` titled "Parliament Verdict". The `──── VERDICT ────` rule and the dim summary table from today's `_render_synthesis` are **removed** in `verdict` level — each callout is its own visually-bordered block; no separator needed. The summary table moves into the saved file's footer (which only appears in `archive` and `full`).

For `full` level, the terminal also prints the First Reading and Debate sections after the verdict block, using the same per-member panels the live in-flight view uses.

### Empty section handling

If a section's content is empty or whitespace-only, the renderer skips it entirely — no empty `> [!warning] Split` block, no empty Rich panel. Recommendation is the one always-rendered exception. If the Speaker somehow produces an empty Recommendation (parser fallback failed), it's rendered with placeholder text `(no recommendation parsed)`.

## 6. Internal architecture

### Module placement

```
src/parliament/render/
├── __init__.py          # existing: DebateRenderer ABC, build_renderer
├── cli_live.py          # existing: RichLiveRenderer (live in-flight)
├── tui_live.py          # existing: CursesLiveRenderer (live in-flight)
└── hansard.py           # NEW: HansardLevel + render_markdown + render_terminal
```

Single new file (~280 LOC). Houses the level enum, the section-inclusion matrix, the markdown renderer, and the terminal renderer. Rationale for not splitting: the two renderers share section-selection and empty-omission logic; ~150 LOC each is well within "one focused module" territory.

### Public API

```python
class HansardLevel(str, Enum):
    MINIMAL = "minimal"
    VERDICT = "verdict"
    ARCHIVE = "archive"
    FULL    = "full"

    @classmethod
    def parse(cls, value: str | None) -> "HansardLevel":
        """Lenient parser: unknown or None values fall back to VERDICT and emit a warning to stderr."""

def render_markdown(hansard: Hansard, level: HansardLevel) -> str:
    """Render a Hansard as Markdown with Obsidian/GitHub callouts."""

def render_terminal(hansard: Hansard, level: HansardLevel, console: Console) -> None:
    """Print a Hansard to the Rich console using callout-mirroring panels."""
```

`HansardLevel(str, Enum)` so it serializes cleanly to YAML and compares to plain strings.

### Section-inclusion matrix

```python
_LEVEL_SECTIONS: dict[HansardLevel, frozenset[str]] = {
    HansardLevel.MINIMAL: frozenset({"question", "recommendation"}),
    HansardLevel.VERDICT: frozenset({"question", "consensus", "split", "risks", "recommendation"}),
    HansardLevel.ARCHIVE: frozenset({"frontmatter", "question", "consensus", "split", "risks", "recommendation", "footer"}),
    HansardLevel.FULL:    frozenset({"frontmatter", "question", "consensus", "split", "risks", "recommendation", "footer", "first_reading", "debate"}),
}

def includes(level: HansardLevel, section: str) -> bool:
    return section in _LEVEL_SECTIONS[level]
```

Single source of truth for "what's in each level." Both renderers consume it.

### Data flow

```
Parliament.ask(question) ─→ Hansard
                              │
            ┌─────────────────┴─────────────────┐
            ▼                                   ▼
  resolve_hansard_level(            resolve_hansard_level(
    cli_flag, config) → level         cli_flag, config) → level
            │                                   │
            ▼                                   ▼
  render_markdown(hansard, level)   render_terminal(hansard, level, console)
            │                                   │
            ▼                                   ▼
   String → save_hansard(...)        Rich panels → user's terminal
            │
            ▼
  ~/.parliament/hansards/YYYYMMDD-HHMMSS-slug.md
```

Both call sites resolve the level the same way; the same level value is used for both outputs in a given run, so what you see and what you save match.

### Refactoring of existing code

| Existing function | New behavior |
|---|---|
| `tui.py::_hansard_markdown(hansard)` | **Deleted.** All callers switch to `render_markdown(hansard, level)`. |
| `tui.py::save_hansard(hansard, save_dir)` | Signature gains `level: HansardLevel`; body delegates to `render_markdown`. |
| `cli.py::_render_synthesis(hansard)` | **Deleted.** Replaced by `render_terminal(hansard, level, console)` at the call site in `ask()`. |
| `cli.py::_render_verbose(hansard)` | **Deleted.** `--verbose` becomes a Click flag that sets `level=FULL`; `render_terminal` handles the full case internally. |
| `cli.py::ask(...)` Click options | Adds `--hansard {minimal,verdict,archive,full}`. `--verbose` retained as alias. |
| `tui.py::_save_show_debate(...)` | Renamed to `_save_settings(...)`; persists both `show_debate` and `hansard.level`. |
| `tui.py::SettingsScreenState` | Gains a `hansard_level: HansardLevel` field; focus enum extended with `"hansard_level"`. |
| `tui.py::_handle_settings_key(...)` | Extended with the cycle widget's Left/Right key handling when `hansard_level` is focused. |
| `tui.py::_draw_app_settings(...)` | Renders the inline cycle widget for the new field. |

### Where the level is resolved

Two call sites in `cli.py::ask`:

```python
level = resolve_hansard_level(cli_flag=hansard_flag, config=config)
if verbose and hansard_flag is None:
    level = HansardLevel.FULL  # back-compat alias

# ... run the debate ...

render_terminal(hansard, level, console)
save_hansard(hansard, save_dir, level=level)
```

The TUI path (`_run_debate`) does the same: resolves the level once after the debate, hands it to `save_hansard`. The TUI doesn't print to a terminal post-run, so there's no `render_terminal` call there — the result screen continues to use today's curses-rendered verdict.

## 7. Test strategy (TDD)

Six new test files, written in dependency order. Each behavior gets one test that fails first, then minimal code to pass.

| # | File | Tests | Concern |
|---|---|---|---|
| 1 | `tests/test_hansard_level.py` | ~12 | `HansardLevel.parse`, `includes(level, section)`, monotonic-hierarchy invariant |
| 2 | `tests/test_resolve_hansard_level.py` | ~10 | CLI > env > config > default precedence (mirrors `test_show_debate_flag.py`) |
| 3 | `tests/test_render_markdown.py` | ~14 | Markdown output per level, callout syntax, empty-section omission, ordering |
| 4 | `tests/test_render_terminal.py` | ~10 | Rich panel output per level, border styles, titles with icons |
| 5 | `tests/test_cli.py` (extend) | ~6 | `--hansard` flag end-to-end, `--verbose` aliasing, env override |
| 6 | `tests/test_tui_settings_screen.py` (extend) | ~8 | Settings screen 3-field cycle widget, `hansard.level` persistence |

**Total: ~60 new tests.**

### Shared fixture

```python
# tests/conftest.py
def make_hansard(
    *,
    consensus: str = "All members agree.",
    split: str = "Disagreement on tactics.",
    risks: str = "- Risk one\n- Risk two",
    recommendation: str = "Proceed.",
    members: list[Member] | None = None,
    first_reading_content: str = "FR content",
    debate_content: str = "Debate content",
) -> Hansard:
    """Build a Hansard with controllable section content. Empty strings omit a section."""
    ...
```

Used across all six new test files. Variant tests pass `split=""` to verify empty-section omission, etc.

### Risk to existing tests

| Existing test | Risk | Adjustment |
|---|---|---|
| `tests/test_cli.py` `_LIVE_*_MARKER` tests | None — live in-flight markers come from the live renderer (governed by `show_debate`); we don't touch that path. |
| `tests/test_tui.py::test_save_hansard_writes_markdown` | High — currently asserts on today's exact markdown shape. Rewritten against the new `verdict`-level output, plus a new `full`-level case to verify back-compat parity with today's shape. |
| `tests/test_progress_events.py` | None | Event protocol; unrelated. |
| `tests/test_renderers.py`, `test_rich_renderer_spinner.py`, `test_curses_renderer.py` | None | Live in-flight renderer tests; orthogonal. |
| `tests/test_tui_settings_screen.py` | Medium — extends from 2 fields to 3. The persistence helper renames from `_save_show_debate` to `_save_settings`. |

Net: ~1 test rewritten, ~3-5 tests extended, all others untouched.

## 8. Migration

This is a **default-changing UX shift** — anyone who runs `parliament ask "..."` without flags will see a meaningfully different (shorter) terminal output and a meaningfully different (shorter) saved `.md` than before. That's intentional and is the core point of the redesign.

| Surface | Migration |
|---|---|
| Existing saved `.md` files | Untouched. New writes use the new format; old files keep their old shape. No retroactive rewriting. |
| Existing config files without `hansard:` section | Resolve to `verdict` default. Users opt up to `archive` or `full` if they want the old behavior. |
| `--verbose` muscle memory | Preserved. Aliases to `--hansard=full`. |
| Bundled example configs (`config.example.yaml`, `config.cloud.yaml`, `config.mixed.yaml`) | Each gets a new `hansard:\n  level: verdict` block with comments explaining the four levels and override paths. |
| `README.md` | New "Hansard detail levels" subsection under Usage, parallel to the "Live debate view" section we just shipped. Includes the precedence table and a sample of each level. |
| `RELEASING.md` / changelog | Note this as a behavior change in the next release: terminal post-run output is now compact by default; pass `--hansard=full` (or the old `--verbose`) to restore the previous chatty output. |

## 9. Estimated diff size

| Area | Lines |
|---|---|
| `src/parliament/render/hansard.py` (new) | ~280 |
| `src/parliament/config.py` (`resolve_hansard_level` + `HansardLevel.parse` re-export) | ~25 |
| `src/parliament/cli.py` (rewire `ask`, drop `_render_synthesis` / `_render_verbose`) | ~30 net |
| `src/parliament/tui.py` (Settings cycle widget, `_save_show_debate` → `_save_settings`) | ~60 |
| Example configs × 3 + README + RELEASING | ~30 |
| Tests (6 files, ~60 tests) | ~600 |
| **Total** | **~1000** |

Roughly the same scale as the live debate view feature shipped over the previous days.

## 10. Out of scope (explicit non-goals)

- **Restyling the live in-flight view** to match the callout palette. Considered in brainstorm as approach C; deferred. The live view is fresh code (days old) and changing its look now risks regressions for a cosmetic-only benefit.
- **Token-level streaming.** Discussed earlier in the session as a separate feature with its own ~340 LOC scope; tracked as an independent follow-up.
- **A "hint" line teaching users about the `--hansard` toggle on every run.** Discoverability happens via `parliament ask --help` and the README; no inline hint.
- **Migrating old saved `.md` files** to the new format. They stay as they are.
- **Per-section override flags** (`--hansard verdict --with debate`). Considered as approach C in Q3; deferred. If a real "I want X but not Y" use case shows up later, this is a clean follow-up addition to the level system.

## 11. Risks / open questions

1. **Obsidian callout multi-line edge cases.** Multi-line callout bodies with bullet lists need `>` on every line (including blank separators). Trusted by spec; verified by eye on a real run during smoke testing. No automated round-trip test through Obsidian's parser.
2. **Recommendation never-empty rule.** If the Speaker's synthesis somehow produces an empty `recommendation`, render a placeholder `(no recommendation parsed)` rather than nothing. Test covers this case.
3. **TUI cycle widget is a new pattern in this codebase.** Today's settings screen has only a checkbox. The 4-state inline cycle gets ~3 dedicated tests on its own (rendering with each level current, key handling for Left/Right wrap-around).
4. **Click flag `--hansard` collision.** None today; `--hansard` is unused in the project's CLI surface.
