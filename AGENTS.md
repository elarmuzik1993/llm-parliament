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
    openai_provider.py   OpenAI API; takes a base_url, so it also serves any
                         OpenAI-compatible endpoint (see model_catalog.py)
    ollama.py            its own class — hardcodes a dummy key, no auth
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

## Scope & invariants

Read this before changing anything that more than one file knows about.

The recurring failure in this repo is not bad code. It is **one fact stored in
several places, where nothing fails when the copies disagree**. Three commits
in recent history exist only to correct documentation the code had already
outgrown -- #49, #57, and `e860096` (stale test counts). Until this section was
written, the **Testing** block below claimed 460 tests against a suite of 482:
a copy nobody was obliged to update, wrong for weeks, breaking nothing.

The cure is not more care. It is fewer copies, and a test on each copy that has
to stay.

**The rule:**

> If a rule is worth stating in this file, it is worth a test that fails when
> it is broken. If it cannot be tested, it is a preference -- put one comment
> at the decision point, and nowhere else.

A convention narrated across four surfaces costs four edits to reverse. That is
what "`groq` and `mistral` stay discovery-only" cost between #43 and #48: it
was written into this file, the README, a docstring *and* a dedicated test,
then reversed one PR later. The test was the only copy that earned its place.

### The five moving parts

Each row is one fact that several places depend on. **Guarded** names the test
that fails when the copies drift; an unguarded row is one a reviewer has to
catch by eye, which is how a careful PR can still leave `doctor.py`'s provider
loop and `docs/configuration.md` behind.

| | The fact | Where it lives | Guarded by |
| --- | --- | --- | --- |
| **A** | Which providers exist, and the key each uses | `model_catalog.OPENAI_COMPATIBLE`, `config.KEY_PROVIDERS`, `providers._OPENAI_COMPATIBLE_PROVIDERS`, `providers._CLOUD_PROVIDERS`, `tui.SUPPORTED_PROVIDERS`, `doctor.PROVIDER_DISPLAY` and its hardcoded loop, `commands.CLOUD_KEY_PROVIDERS`, README, `docs/configuration.md`, this file | partly -- `test_every_wired_provider_has_a_home_for_its_key`. `CLOUD_KEY_PROVIDERS` is the only derived copy of the seven in code |
| **B** | What a model is called | `MODEL_TIERS` (bare ids), `presets.py` constants, OpenRouter `vendor/slug`, Ollama `name:tag` | **nothing.** `get_tier` is an exact dict lookup, so every `vendor/slug` falls to `DEFAULT_TIER` and `detect_gap` can never fire for an OpenRouter parliament (#37) |
| **C** | Which preset wins for an environment | the `if`/`return` ladder in `presets.select_preset` | partly -- `tests/test_first_run_presets.py` covers chosen cases, not the matrix |
| **D** | Where an API key comes from | env var, `keys.env`, keyring, `providers.<name>.api_key` | partly -- precedence is stated under **Config precedence**, and tested per path rather than as a whole |
| **E** | What is true, for a reader | README (five provider sections), `docs/configuration.md`, this file, three shipped YAMLs, `CHANGELOG.md` | only the YAMLs -- `test_shipped_configs_pin_the_built_in_default_level` |

**A** and **B** are load-bearing. **E** is a consequence of A--C rather than an
independent problem, which is why rewriting docs before the code settles is
wasted work.

### Before you add a copy

- **Derive it, or test it.** A new list of provider names, model names or
  preset rules must either be computed from an existing one, or pinned by a
  test that fails when it disagrees with its source. `commands.CLOUD_KEY_PROVIDERS`
  and `test_shipped_configs_pin_the_built_in_default_level` are the two shapes
  to copy.
- **Prefer deleting a copy to correcting it.** The test count this section
  opens with was not updated; it was removed.
- **A young decision goes in one comment**, at the decision point -- not into
  this file, the README and a docstring as well, until it has survived a
  release.
- **Claims about behaviour are claims.** "`parliament doctor` reports each
  wired provider", below, is true only of the providers named in that
  module's own loop. Check a claim in the code before repeating it.

### Direction

The staged plan for collapsing A--E -- one derived provider registry, one
model-identity function, preset selection as data, then the docs split -- is
tracked on the roadmap (#15).

Until the provider registry lands, **adding a vendor costs eleven edits, two of
which CI will not catch.** Finishing the OpenRouter path (#8) is worth more
than adding another vendor.

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

Every PR runs `.github/workflows/ci.yml`: `ruff check .` and
`mypy src/parliament` on Linux, and `python -m pytest -q` on Linux
(3.11/3.12/3.13), macOS, and Windows. Run all three locally before pushing.

Issues carry `good first issue` and `help wanted` labels; small, well-scoped
gaps should be filed as issues with those labels rather than fixed silently, so
that new contributors have somewhere to land.

### Commit identity

If you are an agent committing on someone's behalf, do not commit as yourself.
Before running `git commit`, make sure `git config user.name` / `user.email`
resolve to the human you're working for, not the agent's own default identity
(e.g. `claude <noreply@anthropic.com>`) — an unconfigured identity gets
attributed to whatever account GitHub matches that email to, not to the person
who actually did the work.

The human is then the sole author and the commit carries no trailer crediting
the assistant — see **No AI attribution** under Commit & PR conventions above,
which governs this and overrides any harness default that adds one.

### Testing

```bash
python -m pytest -q          # must pass before any commit
ruff check .                 # must be clean before any commit
mypy src/parliament          # must pass before any commit
```

Dev deps (`pytest`, `pytest-asyncio`, `ruff`, `mypy`) are in `pyproject.toml` under
`[project.optional-dependencies] dev`. Install via `pipx inject` or `pip install -e ".[dev]"`.

The mypy config is a permissive baseline to ratchet rather than a full type
gate: with only `ignore_missing_imports`, unannotated function bodies are not
checked at all. Treat a green run as “nothing already annotated regressed”.

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

Two shapes exist today, and they are not interchangeable -- pick the one that
matches the SDK you have.

#### OpenAI-compatible registry row (no new class needed)

For any service that speaks the OpenAI API at its own address (`OpenRouter`
today). The model picker's discovery is already covered by a row in
`model_catalog.OPENAI_COMPATIBLE`; wiring it as a usable `provider:` value is
three steps:

1. Add the address and the key variable to `OPENAI_COMPATIBLE` in
   `model_catalog.py`.
2. Add the provider to `KEY_PROVIDERS` in `config.py` so `parliament keys set`
   knows the variable and `parliament doctor` reports it.
3. Add the provider name to `_OPENAI_COMPATIBLE_PROVIDERS` in
   `providers/__init__.py` -- this is what opts the row in as a wired
   provider. Discovery (`groq`, `mistral`) and wiring (`openrouter`) are
   deliberately separate: a name that has a row but is not in the tuple is
   still an error in a config, because the README documents `provider: groq`
   that way too.

`create_provider(...)` builds the client by reusing `OpenAIProvider` with the
registry row's `base_url` and `env_var`. A missing vendor key is a hard error
-- `AsyncOpenAI(api_key=None)` would silently read `OPENAI_API_KEY` from the
process environment and post an OpenAI credential to the other vendor (#48).

#### Cloud-native SDK

For a vendor whose SDK is not OpenAI-compatible (`anthropic`, `google` today):

1. Subclass `Provider` in `providers/base.py`.
2. Add the provider key to `KEY_PROVIDERS` in `config.py`.
3. Add it to `_CLOUD_PROVIDERS` in `providers/__init__.py` (the lazy-import
   table), and wire the member in `config.py::build_parliament_from_config()`.
4. Add model presets to `model_catalog.py`.

#### Both shapes

- `parliament doctor` reports each wired provider. For the registry shape, the
  SDK import is covered by whichever entry maps to the underlying SDK
  (`openrouter` reuses the `openai` SDK row); the doctor only needs the key
  check.
- The TUI's `SUPPORTED_PROVIDERS` list in `tui.py` gates both the provider
  picker and `_save_member_edit`. Add a new wired provider there too, or it
  can be named in a config but not edited from the TUI.

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
