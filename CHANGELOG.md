# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
