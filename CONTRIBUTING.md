# Contributing to LLM Parliament

**Contributions are welcome and actively wanted.** This project is early, the
maintainer is new to open source, and there is plenty of low-hanging fruit.
Bug reports, typo fixes, terminal-compatibility reports, docs, and code are all
equally valuable — no contribution is too small.

- 🌱 **New here?** Start with a
  [good first issue](https://github.com/elarmuzik1993/llm-parliament/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
- 🙋 **Want something bigger?** See
  [help wanted](https://github.com/elarmuzik1993/llm-parliament/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
  and the [roadmap](https://github.com/elarmuzik1993/llm-parliament/issues/15).
- 💬 **Not sure yet?** Ask in
  [Discussions](https://github.com/elarmuzik1993/llm-parliament/discussions) —
  questions are not noise.

You do not need permission to open a PR. For anything large or architectural,
opening an issue first saves you from building something that gets redirected.

---

## Claiming an issue

**Comment on the issue before you start building.** One line is enough — "taking
this" does the job. The maintainer will assign it to you, which puts your name on
the issue list so the next person can see it's taken.

This exists because it already cost someone an afternoon. Two contributors
independently built the same feature twelve minutes apart; both PRs were good,
only one could merge, and the other had to close. Nothing on the issue told
either of them the other was there.

The rules are deliberately loose:

- **Small changes don't need this.** A typo, a docs line, a one-function fix —
  just open the PR. Coordinating costs more than the occasional duplicate.
- **A claim isn't a lock.** If an assigned issue goes quiet for about two weeks,
  it's fair game again. Life happens and stalled claims shouldn't block the
  queue. If you're still on it and just slow, say so on the issue and it stays
  yours — nobody is counting days.
- **Unclaiming is free and always fine.** "Turned out to be more than I wanted to
  take on" is a completely respectable comment, and far more useful than silence.

If you want something to work on and nothing is obviously free, ask in
[Discussions](https://github.com/elarmuzik1993/llm-parliament/discussions) or
comment on the [roadmap](https://github.com/elarmuzik1993/llm-parliament/issues/15).

## Branch from current `main`

Fetch and branch fresh before you start:

```bash
git remote add upstream https://github.com/elarmuzik1993/llm-parliament.git
git fetch upstream main
git checkout -b my-change upstream/main
```

CI is new, and a branch cut before it landed won't get a check run at all — the
PR will just sit there with nothing reported, which looks like something is
broken when it isn't. Branching from current `main` avoids that.

One more thing worth knowing, so it doesn't look like your PR is being ignored:
**the first workflow run on a PR from a fork needs the maintainer to approve it.**
That's a GitHub default, not a judgement about your change. If your checks show
as pending or absent, that's usually why.

---

## Ways to help that aren't code

- **Run `parliament doctor` on your machine** and report the result on
  [#14](https://github.com/elarmuzik1993/llm-parliament/issues/14). The TUI
  touches curses, colours, and Unicode — every OS/terminal combination reported
  is real signal.
- **Tell us where the docs lie.** If a command in the README doesn't do what it
  says, that's a bug worth an issue.
- **Share a Hansard.** Interesting debates make good examples.

---

## Setup

```bash
git clone https://github.com/elarmuzik1993/llm-parliament.git
cd llm-parliament

python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Nothing else is required. There is a deterministic mock provider, so you can run
a full debate with no API keys and no Ollama:

```bash
parliament ask "What should we test first?" --mock
parliament --mock                 # the TUI, on mock providers
parliament doctor                 # health check
```

## The dev loop

```bash
python -m pytest -q         # full suite — must be green
ruff check .                # must be clean
mypy src/parliament         # must pass
```

All three run in CI: pytest on Linux, macOS, and Windows across Python
3.11–3.13; Ruff and mypy on Linux. Running them locally before pushing means
CI rarely surprises you.

The mypy config is a permissive baseline to ratchet, not a full type gate.
With only `ignore_missing_imports` set, mypy skips the bodies of unannotated
functions, so “mypy passes” currently means “nothing already annotated is
wrong” rather than “the codebase is typed”. Tightening it is incremental work,
not a prerequisite for contributing.

Useful subsets while iterating:

```bash
python -m pytest tests/test_tui.py -q          # one file
python -m pytest -q -k hansard                 # by name
python -m pytest -q -x                         # stop at first failure
```

## Where things live

Read [AGENTS.md](AGENTS.md) first — it is the source of truth for architecture
and conventions (and it is written to be readable by AI coding assistants as
well as humans; `CLAUDE.md` and `GEMINI.md` just point at it).

The short version:

| If you want to change… | Start in |
|---|---|
| CLI commands and flags | `src/parliament/cli.py`, `src/parliament/config.py` |
| The curses TUI | `src/parliament/tui.py` |
| Slash commands (`/help`, `/doctor`, …) | `src/parliament/commands.py` |
| Debate phases | `src/parliament/procedures/` |
| A model provider | `src/parliament/providers/` |
| Hansard output and live views | `src/parliament/render/` |
| Model presets shown in pickers | `src/parliament/model_catalog.py` |

### Recipe: add a provider

1. Subclass `Provider` in `providers/base.py`.
2. Add the provider key to `KEY_PROVIDERS` in `config.py`.
3. Wire it into `config.py::build_parliament_from_config()`.
4. Add model presets to `model_catalog.py`.
5. Add tests — model the happy path on `providers/mock.py` and the failure path
   on `tests/test_provider_errors.py`.

### Recipe: add a slash command

1. Write `def _mycommand(args: str, ctx: CommandContext) -> CommandResult` in
   `commands.py`.
2. Append a `Command(...)` entry to the `COMMANDS` list at the bottom of the file.
3. The TUI palette and `/help` pick it up automatically — no other wiring.

## House rules

- **Ruff is the style authority.** `ruff check .` clean, line length 100.
- **No `print()` in library code** — use `console.print()` (CLI) or curses draws (TUI).
- **All curses text goes through** `_add_line()` (`tui.py`) or `_safe_addstr()`
  (`tui_live.py`), never `addstr`/`addnstr` directly. PDCurses on Windows is not
  thread-safe: `emit()` mutates state, `redraw()` draws, and drawing only ever
  happens on the main thread.
- **Type annotations** on new functions; `from __future__ import annotations` at
  the top of new modules.

## Submitting a PR

Before you open it:

- [ ] The issue it closes is claimed and assigned to you (see
      [Claiming an issue](#claiming-an-issue)) — or it's small enough not to need it
- [ ] The branch is cut from current `main`
- [ ] `python -m pytest -q` passes
- [ ] `ruff check .` is clean
- [ ] `mypy src/parliament` passes
- [ ] New behaviour has a test; a bug fix has a regression test
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` if the change is user-visible
- [ ] No debug prints, no commented-out code

What makes review fast:

- **Focused** — one logical change per PR. Two unrelated fixes are two PRs.
- **Described** — say *why*, not just *what*. Link the issue it closes.
- **Honest** — "I couldn't test this on Windows" is useful information, not a
  weakness. Say it in the PR body.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
loosely — `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, with an
optional scope (`fix(tui): …`). Not enforced by a bot; it just keeps
`CHANGELOG.md` easy to assemble.

AI-assisted contributions are fine. Review the output before you send it — you
are the author of your PR, and you should be able to explain every line in it.
That includes the git identity: coding agents often default to committing as
`claude <noreply@anthropic.com>` (or similar) when no local git identity is
configured, which credits the tool as author instead of you in GitHub's
contributor graphs. Set `git config user.name`/`user.email` to your own
before committing.

This project does not use AI attribution trailers — no `Co-Authored-By:` for a
model or agent, and no generated-by footers in PR descriptions. The contributor
is the author.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include
your `parliament doctor` output — it captures OS, Python, terminal size, and
provider reachability in one paste. Redact API keys.

For security issues, follow [SECURITY.md](SECURITY.md) instead — do not open a
public issue.

## Feature requests

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
Describe the problem you hit before the solution you want; it often turns out
there's a simpler fix.

---

By contributing you agree that your contributions are licensed under the
[AGPL-3.0](LICENSE), and to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
