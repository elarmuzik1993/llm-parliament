# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`openrouter` provider** — OpenRouter speaks the OpenAI API at its own
  address, so it needs no class of its own: it reuses `OpenAIProvider` with the
  address and the `OPENROUTER_API_KEY` variable read from its
  `model_catalog.OPENAI_COMPATIBLE` row. A member can now name
  `provider: openrouter` instead of pointing `openai` at a `base_url`, and
  because `openrouter` is in `KEY_PROVIDERS`, `parliament keys set openrouter`,
  `keys list`, the TUI's `/key`, and the doctor's key check all follow with no
  further wiring. The `groq` and `mistral` registry rows stay discovery-only.
  Fixes #36.

- **`degraded` on `Hansard`** — `true` when the verdict was reached with fewer
  members than configured because one or more members failed with a provider
  error. Degraded mode itself is unchanged, but `--json` consumers can now tell
  a three-member verdict from a two-member one without re-deriving it from the
  response arrays. Documented in `docs/hansard-schema.md`. Fixes the second half
  of #34.

- **`parliament --version`** — prints the installed version and exits 0, via
  Click's `version_option` (also exposed as `-V`); the version comes from
  `parliament.__version__`, which is read from package metadata so it cannot
  drift from `pyproject.toml`, falling back to `"unknown"` when running from an
  uninstalled source tree. `parliament doctor` reports it first, ahead of the
  Python line. Fixes #19. The `"unknown"` fallback and four of the tests come
  from @dchaudhari7177's #25.
- `parliament ask --json` now prints the complete Hansard object for scripts,
  with `docs/hansard-schema.md` documenting the fields and common `jq` recipes.
- **CI** — `.github/workflows/ci.yml` runs `ruff` plus the full pytest suite on
  Linux, macOS, and Windows across Python 3.11-3.13 for every push and PR.
- Issue chooser links (`.github/ISSUE_TEMPLATE/config.yml`) pointing at good
  first issues, Discussions, the security policy, and the contributing guide.

### Changed

- **Default Hansard level is now `verdict`** (the full four-part synthesis),
  reversing the 0.2.0 change to `minimal`. The split — where the members
  disagreed and why — is the one output a single model cannot produce, and
  defaulting to the recommendation alone made a three-member debate read like
  an expensive single call. `config.cloud.yaml` and `config.mixed.yaml` already
  shipped `level: verdict`; the built-in default and `config.example.yaml` were
  the outliers, and the three are now pinned to agree by test.

  This affects on-screen output only: saved `.md` files are still always
  written at `archive`, and `--json` was never gated by level. `minimal` is
  unchanged and still available via `--hansard=minimal`,
  `PARLIAMENT_HANSARD_LEVEL`, or `hansard.level` in config.

  **Existing installs keep the level already written in their config.** The
  first-run wizard materializes `hansard.level`, so a config created before
  this release still says `minimal` and is left untouched — change it in the
  TUI settings screen or by editing `~/.parliament/config.yaml`.
- The default and the typo-recovery value are now one constant,
  `render.hansard.DEFAULT_LEVEL`, instead of being spelled `MINIMAL` four
  times inside `HansardLevel.parse`.
- `CONTRIBUTING.md` expanded — non-code ways to help, mock-only dev loop, a
  change-area-to-file map, recipes for adding a provider or slash command, and
  an explicit PR checklist.
- README gained CI / PRs-welcome / good-first-issue / help-wanted badges, a
  Contributing section, and a "For AI agents and automated tools" section.
- AGENTS.md repository layout now lists `first_run.py`, `presets.py`,
  `providers/errors.py`, `docs/`, and `.github/`.

### Fixed

- README development setup installed the non-existent `all` extra
  (`pip install -e ".[all,dev]"`); it now installs `".[dev]"`.
- Dev extra pins `ruff>=0.8,<0.16`. Ruff 0.16 widened its default rule set, so
  an unpinned install reported 97 findings on unchanged code while an older one
  reported none; see #30 for the decision on adopting the new defaults.
- README and AGENTS.md still documented `verdict` as the built-in default
  Hansard level; it has been `minimal` since 0.2.0. Both now also state that
  saved `.md` files are always written at `archive` level.
- **A cancelled member no longer shrinks the debate.** `run_first_reading()` and
  `run_debate()` filtered gather results with `isinstance(r, Exception)`, which
  `CancelledError` fails (it is a `BaseException`), so a cancelled member was
  returned as if it were a `Response` — a function annotated `-> list[Response]`
  returning exception objects. Cancellation now aborts the debate instead. This
  also fixes the case that motivated #34: a Ctrl-C or an enclosing
  `asyncio.timeout` during First Reading dropped one member and kept going, so a
  timeout could return a confident verdict built from fewer members than
  configured. Provider failures still degrade as before. Fixes #34.
- `parliament ask` exits 130 with "Debate cancelled." on `CancelledError`, not
  just `KeyboardInterrupt`; previously a `CancelledError` escaping
  `asyncio.run()` missed the `except Exception` handler and printed a traceback.

### Fixed

- `parliament ask --json` no longer hides member failures. A provider that
  drops out mid-debate is reported on stderr instead of silently shrinking the
  response arrays.
- `parliament ask --json` now writes warnings and errors to stderr, keeping
  stdout a clean JSON document for `jq` and other consumers.
- **`openrouter` no longer borrows `OPENAI_API_KEY`.** Building a client for a
  wired OpenAI-compatible provider used to leave `api_key` unset when the
  vendor's own variable was missing, and the OpenAI SDK silently fell back to
  `OPENAI_API_KEY` -- so a real OpenAI credential would be posted to another
  vendor without anyone noticing. Construction now raises a clear error that
  names the missing variable and the recovery command, and the model picker
  uses the same rule (`openai_compatible_key()` returns `None` for any row
  that has its own `KEY_PROVIDERS` entry, instead of borrowing). The
  discovery-only rows (`groq`, `mistral`) keep the `OPENAI_API_KEY` fallback,
  because they have no key home of their own. Fixes #48.

## [0.2.0] — 2026-05-19

### Added

- **First-run config wizard** — detects API keys, Ollama models, and system
  RAM on first launch and writes a tailored preset; 8 factory presets covering
  cloud-full, cloud-anthropic/openai/google, mixed, local-safe,
  mock-ollama-hint, and mock. Wizard fires interactively when stdin is a TTY;
  writes silently with a stderr notice on non-TTY (e.g. pipx postinstall).
  Fixes USE-20.
- **Resilient parliament** — provider failures drop that member and the debate
  continues with survivors; Division Speaker is chosen only from debate
  survivors with a retry loop; `is_fatal_provider_error()` gates reraise vs
  drop. Fixes USE-35.
- **Human-readable provider errors** — `providers/errors.py::format_provider_error()`
  covers OOM, timeout, 429/rate-limit, auth, and model-not-found across all
  three cloud providers. Fixes USE-21.
- **OS keyring integration** — `parliament keys set` saves to the OS native
  credential store (Windows Credential Manager, macOS Keychain, GNOME Keyring)
  with automatic fallback to `keys.env`; `parliament keys migrate` moves
  existing file keys to the keyring; `load_keys()` falls back to keyring for
  any key not found in the file. Fixes USE-31.
- **`parliament keys migrate`** — one-command migration of `keys.env` to the
  OS keyring; renames `keys.env → keys.env.bak` on full success.
- **`parliament update`** slash command + CLI subcommand — detects install
  type (editable git / pipx / pip-user / pip-system) and runs the matching
  upgrade command. Fixes USE-29.
- **Member viability section in `parliament doctor`** — lists each configured
  member with key/model status and aggregate RAM footprint check (via psutil).
- **Gemini 2.5 Flash default** — `gemini-2.5-flash` replaces
  `gemini-2.0-flash-lite` as the default Google model in presets and
  `MODEL_TIERS`. Fixes USE-36.
- **TUI result pager improvements** — Page Down (Space/PgDn/f), Page Up
  (PgUp/u), jump to top (g), jump to bottom (G) added to the Hansard viewer.

### Changed

- **Default Hansard level is now `minimal`** (recommendation only) for both
  display and new configs; saved `.md` files are always written at `archive`
  level (full synthesis + frontmatter) regardless of display level.
- **`parliament keys remove`** now clears the OS keyring in addition to
  `keys.env`.
- **Result pager footer** reads "Read full report: {path}" pointing to the
  saved archive-level Hansard file.

### Fixed

- Stray leading `**` markdown markers stripped from parsed Synthesis fields.
  Fixes USE-30.

### Dependencies

- Added `psutil>=5.9` (RAM detection in wizard and doctor).
- Added `keyring>=24.0` (OS credential store integration).

## [0.1.0] — 2026-05-18

First publishable release. Three LLM members debate a question through First
Reading, Debate, and Division phases and produce a structured Hansard verdict.

### Added

- **Parliamentary debate engine** — three-phase pipeline (First Reading,
  Debate, Division) with parallel provider calls and a Speaker synthesis step.
- **Providers** — Anthropic, Google, OpenAI, Ollama (via OpenAI-compatible
  endpoint), plus a deterministic Mock provider for testing.
- **Curses TUI** — interactive dashboard with member picker, settings screen,
  slash-command palette, and Hansard result viewer.
- **CLI** (`parliament ask`) — one-shot debates with Rich output and a live
  debate renderer (spinner + elapsed timer per pending member).
- **`parliament doctor`** — health check covering Python version, curses
  availability, terminal capabilities, config initialization, provider SDKs,
  API keys, and Ollama daemon reachability. Available as a slash command in
  the TUI as well.
- **Hansard detail levels** — `HansardLevel` enum (`minimal`, `verdict`,
  `archive`, `full`) controls how much of the debate is rendered. Configurable
  via `--hansard` CLI flag, `PARLIAMENT_HANSARD_LEVEL` env var, config file,
  or TUI settings screen (with `--verbose` kept as a back-compat alias).
- **Slash commands** — `/help`, `/doctor`, `/update`, `/history`, `/copy`,
  speaker-override, and members-picker shortcuts.
- **`/update`** — pull latest code for editable git installs from inside the
  TUI; shows a centered quit-notice before exit so users see the result.
- **Render diagnostic script** (`scripts/diagnose-render.py`) — verifies
  terminal colour and spinner behaviour for debugging environment issues.
- **Windows support** — `windows-curses` dependency, asyncio Windows event
  loop policy, forced Rich terminal mode, cross-platform path resolution in
  `/update`.
- **Docs** — `AGENTS.md` (source of truth), `CLAUDE.md` / `GEMINI.md`
  pointers, `RELEASING.md`, per-OS install instructions, hansard-redesign
  plan and spec.

### Fixed

- Curses thread race on Windows — all curses drawing now happens on the main
  thread; the worker thread only mutates renderer state.
- Synthesis parser now handles markdown (`### CONSENSUS`) and bold
  (`**CONSENSUS**`) section headers in addition to plain `CONSENSUS:`.
- Settings screen UX — left arrow cycles hansard level; `save_dir` requires
  Enter to enter edit mode (no accidental edits from focus changes).
- Curses colour pairs are re-initialised after the live renderer resets them,
  so the dashboard regains colour on return.
- Rich colours forced on Windows (`force_terminal=True`, `legacy_windows=False`).
- `/update` resolves `file://` URLs from `direct_url.json` correctly on
  Windows (uses `url2pathname`, not `urlparse`).

### Notes

- Default config is created at `~/.parliament/config.yaml` (Linux/macOS) or
  `%USERPROFILE%\.parliament\config.yaml` (Windows) on first run.
- API keys are stored in `keys.env` next to the config, `chmod 0600` on Unix.
- Test suite: 321 tests passing under `pytest -q`; `ruff check .` clean.

[0.1.0]: https://github.com/elarmuzik1993/llm-parliament/releases/tag/v0.1.0
