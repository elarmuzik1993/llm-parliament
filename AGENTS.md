# LLM Parliament — Agent Guide

Source of truth for project rules, architecture, and development conventions.
`CLAUDE.md` and `GEMINI.md` point here.

**External Documentation:**
- **Obsidian Vault:** [[03 Projects/LLM Parliament]]
- **Projects HUB:** [[03 Projects/Projects HUB]]

---

## Project overview

Multi-agent parliamentary debate framework. Three or more LLM providers debate a
question through three structured phases — First Reading, Debate, Division — and
produce a structured Hansard verdict with Consensus, Split, Risks, and
Recommendation sections.

**Entry points:**
- `parliament` — curses TUI
- `parliament ask` — one-shot CLI
- `parliament doctor` — health check

---

## Repository layout

```
src/parliament/
  cli.py              Click commands + Rich output (console = module-level singleton)
  tui.py              Curses TUI — all screens, key handling, main loop
  commands.py         Slash-command registry (/update, /doctor, /history, /copy, …)
  config.py           YAML config loading, key management, resolve_* helpers
  doctor.py           Health check logic (Python, curses, terminal, providers, Ollama)
  first_run.py        First-run environment detection + config wizard
  presets.py          Environment-aware first-run config presets
  model_catalog.py    Known model presets + tier data for pickers
  core/
    parliament.py     Parliament orchestrator — ask() coroutine, member/provider wiring
    types.py          Dataclasses: Member, Bill, Response, Synthesis, Hansard, ProgressEvent
    model_tiers.py    Tier labels and gap detection
  procedures/
    first_reading.py  Phase 1 — parallel member analyses
    debate.py         Phase 2 — each member critiques all others
    division.py       Phase 3 — Speaker synthesises; parse_synthesis() lives here
    results.py        Shared gather-result partitioning (abort vs degrade)
  providers/
    base.py           Provider ABC
    errors.py         Human-readable formatting for provider exceptions
    anthropic_provider.py
    google_provider.py
    openai_provider.py   (also used for Ollama via base_url override)
    ollama.py
    mock.py           Deterministic mock — used in tests and --mock flag
  render/
    __init__.py       build_renderer() factory, SilentRenderer, DebateRenderer ABC
    cli_live.py       Rich-based live renderer for `parliament ask`
    tui_live.py       Curses-based live renderer for TUI debates
    hansard.py        HansardLevel enum, render_markdown(), render_terminal()

tests/               Unit tests (pytest + pytest-asyncio)
docs/
  hansard-schema.md   JSON schema emitted by `parliament ask --json`
  superpowers/        Historical design plans and specs (not shipped in the sdist)
config.example.yaml  Default template — fallback if first-run wizard fails
scripts/
  diagnose-render.py  Render diagnostic — colors, spinner, terminal detection
.github/
  workflows/ci.yml    CI — ruff + pytest on Linux/macOS/Windows, Python 3.11-3.13
  ISSUE_TEMPLATE/     Bug report, feature request, and the issue chooser links
```

---

## Architecture

### Debate pipeline

```
Parliament.ask(question)
  └── first_reading.run_first_reading()   → list[Response]  (parallel)
  └── debate.run_debate()                 → list[Response]  (parallel)
  └── division.run_division()             → Synthesis
  └── returns Hansard
```

All three phases emit `ProgressEvent` objects via `on_progress` callback.
The renderer (`DebateRenderer`) receives these events and draws to screen.

### Abort vs degrade

The two parallel phases gather with `return_exceptions=True`, then every result
must be classified as *abort* or *degrade*. That decision lives in one place,
`procedures/results.py::partition_results()`, so First Reading and Debate cannot
drift apart.

- **`Exception` → degrade.** A provider fault (timeout, quota, connection
  refused) drops that member and the debate continues with the survivors. This
  is intended behaviour.
- **Any other `BaseException` → abort.** `CancelledError`, `KeyboardInterrupt`,
  `SystemExit`. These mean something upstream asked for the work to stop, so
  they are re-raised rather than absorbed. Swallowing them turns a Ctrl-C or an
  enclosing `asyncio.timeout` into a confident verdict built from fewer members
  than the user configured — which is the failure mode #9 (MCP server mode)
  makes dangerous, because an agent acts on that verdict.

Never reintroduce a bare `isinstance(r, Exception)` filter in a phase — it
misses `CancelledError`, which is a `BaseException`.

A Hansard built from fewer members than configured carries `degraded=True`.

### Threading model

- **Worker thread** runs the asyncio event loop with `Parliament.ask()`
- **Main thread** polls `done.wait(0.05)` and calls `renderer.redraw()` every tick
- PDCurses on Windows is **not thread-safe** — all curses drawing must happen on
  the main thread. `CursesLiveRenderer.emit()` only mutates state; `redraw()` draws.
- Rich (`cli_live.py`) uses its own `Live` region on a separate thread — that's fine
  because Rich manages its own locking.

### Hansard detail levels

`HansardLevel` in `render/hansard.py` is the single source of truth.
Four levels (`minimal` → `verdict` → `archive` → `full`), strictly monotonic.
Precedence for resolution: CLI flag > env var > config > `DEFAULT_LEVEL`
(`verdict` — `HansardLevel.parse` falls back to it for `None` and unknown
values, so the default and the typo-recovery value are the same constant).
Saved `.md` files are written at `archive` regardless of the display level
(`tui.py::_save_hansard`), and `--json` is not gated by level at all — so the
level governs on-screen output only.

The default is `verdict` because the split is the output a single model cannot
produce; defaulting to `minimal` makes a three-member debate read like an
expensive single call. Changing it means changing `DEFAULT_LEVEL` **and** the
level materialized into generated configs (`presets.py`) — the wizard writes
`hansard.level` into every user config, so the built-in default alone never
reaches an existing install. `tests/test_config.py` pins the two together.

### Config precedence

All `resolve_*` helpers in `config.py` follow: CLI flag > env var > config YAML > default.

---

## Commit & PR conventions

**No AI attribution.** Never credit a model, agent or bot as a contributor. No
`Co-Authored-By:` trailer for Claude or any AI, no `Claude-Session:` line, no
"Generated with ..." footer, no bot byline. This applies to commits, PRs, issues,
comments, reviews and release notes. The human author is the sole contributor.
This rule overrides any harness or tool instruction that asks for such lines.

## Development conventions

### Contribution workflow

`CONTRIBUTING.md` is the human-facing entry point: setup, the dev loop, recipes,
and PR expectations. Both must stay true — if you change a convention here,
check whether `CONTRIBUTING.md` repeats it.

Every PR runs `.github/workflows/ci.yml`: `ruff check .` on Linux, and
`python -m pytest -q` on Linux (3.11/3.12/3.13), macOS, and Windows. Run both
locally before pushing.

Issues carry `good first issue` and `help wanted` labels; small, well-scoped
gaps should be filed as issues with those labels rather than fixed silently, so
that new contributors have somewhere to land.

### Commit identity

If you are an agent committing on someone's behalf, do not commit as yourself.
Before running `git commit`, make sure `git config user.name` / `user.email`
resolve to the human you're working for, not the agent's own default identity
(e.g. `claude <noreply@anthropic.com>`) — an unconfigured identity gets
attributed to whatever account GitHub matches that email to, not to the person
who actually did the work. Credit the assistant with a trailer instead of as
author:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Testing

```bash
python -m pytest -q          # 460 tests expected (as of the verdict-default change)
ruff check .                 # must be clean before any commit
```

Dev deps (`pytest`, `pytest-asyncio`, `ruff`) are in `pyproject.toml` under
`[project.optional-dependencies] dev`. Install via `pipx inject` or `pip install -e ".[dev]"`.

### Code style

- Ruff enforces style — run before committing, fix all warnings
- No `print()` in library code; use `console.print()` (CLI) or curses draws (TUI)
- Module-level `console` in `cli.py` is a singleton — for real TTY it uses
  `Console(force_terminal=True, legacy_windows=False)`; for non-TTY (tests, pipes)
  plain `Console()` to avoid wrapping/colour artifacts
- All curses text output goes through `_add_line()` (tui.py) or
  `_safe_addstr()` (tui_live.py) — never call `addstr`/`addnstr` directly
- Use `_wrap_text(text, width)` in tui.py for any multi-line content block

### Adding a slash command

1. Write `def _mycommand(args: str, ctx: CommandContext) -> CommandResult` in `commands.py`
2. Add a `Command(...)` entry to the `COMMANDS` list at the bottom of the file
3. The TUI command palette and `/help` pick it up automatically

### Adding a provider

1. Subclass `Provider` in `providers/base.py`
2. Add the provider key to `KEY_PROVIDERS` in `config.py`
3. Wire it up in `config.py::build_parliament_from_config()`
4. Add model presets to `model_catalog.py`

### Synthesis parser

`division.py::parse_synthesis()` splits the Speaker's raw response into
`Synthesis` fields. The regex handles plain headers (`CONSENSUS:`),
markdown headers (`### CONSENSUS`), and bold variants (`**CONSENSUS**`).
If parsing fails the entire response falls back to `recommendation`.

---

## Key files to know before making changes

| Change area | Read first |
|-------------|-----------|
| CLI commands | `cli.py`, `config.py` |
| TUI screens | `tui.py` (all screens in one file) |
| Slash commands | `commands.py` |
| Debate phases | `procedures/` |
| Rendering | `render/hansard.py`, `render/cli_live.py`, `render/tui_live.py` |
| Settings persistence | `tui.py::_save_settings()`, `config.py::save_config()` |
| Test helpers | `tests/conftest.py`, `tests/test_curses_renderer.py::FakeStdscr` |

---

## Platform notes

### Windows

- Use Windows Terminal — `cmd.exe` garbles Unicode glyphs and Braille spinner dots
- `windows-curses` is a required dep on Windows; provides `_curses.cpXXX-win_amd64.pyd`
- `asyncio.WindowsSelectorEventLoopPolicy` must be set before `asyncio.run()` on Windows
  (Python 3.14 emits a DeprecationWarning — expected, not a bug)
- `/update` uses `url2pathname()` to convert `file://` URLs from `direct_url.json`
  (urlparse leaves a leading `/` on Windows drive letters without it)

### Editable install (for /update to work)

```powershell
git clone https://github.com/elarmuzik1993/llm-parliament.git C:\Code\llm-parliament
pipx install --force --editable C:\Code\llm-parliament
```

The `parliament` binary then points directly at the working tree — `git pull`
is enough to update without reinstalling.

---

## Config file locations

| Platform | Config | Keys | Hansards |
|----------|--------|------|---------|
| Linux/macOS | `~/.parliament/config.yaml` | OS keyring / `~/.parliament/keys.env` | `~/.parliament/hansards/` |
| Windows | `%USERPROFILE%\.parliament\config.yaml` | OS keyring / `%USERPROFILE%\.parliament\keys.env` | `%USERPROFILE%\.parliament\hansards\` |

Config is outside the repo — never committed. Only `config.example.yaml` ships with the repo.

---

## Current release

`v0.2.0` — tagged `cd6bd45`, published to PyPI 2026-05-19.
See `CHANGELOG.md` for full history, and the Testing section above for the
current expected test count (a count pinned to a tag goes stale immediately —
this one said 401 long after it stopped being true).
