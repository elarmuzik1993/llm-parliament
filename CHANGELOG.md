# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
