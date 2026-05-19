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
  model_catalog.py    Known model presets + tier data for pickers
  core/
    parliament.py     Parliament orchestrator — ask() coroutine, member/provider wiring
    types.py          Dataclasses: Member, Bill, Response, Synthesis, Hansard, ProgressEvent
    model_tiers.py    Tier labels and gap detection
  procedures/
    first_reading.py  Phase 1 — parallel member analyses
    debate.py         Phase 2 — each member critiques all others
    division.py       Phase 3 — Speaker synthesises; parse_synthesis() lives here
  providers/
    base.py           Provider ABC
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
config.example.yaml  Default template — copied to ~/.parliament/config.yaml on first run
scripts/
  diagnose-render.py  Render diagnostic — colors, spinner, terminal detection
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
Precedence for resolution: CLI flag > env var > config > default (`verdict`).

### Config precedence

All `resolve_*` helpers in `config.py` follow: CLI flag > env var > config YAML > default.

---

## Development conventions

### Testing

```bash
python -m pytest -q          # 321 tests expected (as of Animation branch)
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
git clone -b Animation https://github.com/elarmuzik1993/llm-parliament.git C:\Code\llm-parliament
pipx install --force --editable C:\Code\llm-parliament
```

The `parliament` binary then points directly at the working tree — `git pull`
is enough to update without reinstalling.

---

## Config file locations

| Platform | Config | Keys | Hansards |
|----------|--------|------|---------|
| Linux/macOS | `~/.parliament/config.yaml` | `~/.parliament/keys.env` | `~/.parliament/hansards/` |
| Windows | `%USERPROFILE%\.parliament\config.yaml` | `%USERPROFILE%\.parliament\keys.env` | `%USERPROFILE%\.parliament\hansards\` |

Config is outside the repo — never committed. Only `config.example.yaml` ships with the repo.

---

## Current branch status (Animation)

Branch: `origin/Animation` — tip `23eaab9`
Windows testing: ✅ complete (321 tests passing, ruff clean)
Linux testing: pending
PR to main: blocked on Linux verification

See `docs/superpowers/plans/2026-05-09-hansard-redesign.md` for the full
implementation plan behind this branch.
