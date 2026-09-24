<!-- Hand-off between sessions on any machine, local or cloud. AGENTS.md imports it, so every
     session starts with it. The hand-off rewrites it; it is not a log, and history belongs in git.
     Keep it under ~40 lines; the SessionStart hook warns past 60. -->
# State

_Updated 2026-09-24_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). CI is green:
  ruff and mypy clean, 553 tests.
- `chore/agent-workflow`: the agent workflow moves into `AGENTS.md` and `.agents/`, CLAUDE.md is
  removed, and `scripts/verify.sh` runs the CI checks in one command.

## Next
1. OpenRouter series: #37 (catalog presets), then #39 (docs and doctor). Order taken from the
   issue titles; priority `unverified`.
2. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly, so CLAUDE.md is gone and
  agent state lives under neutral names in `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.

## Known issues
- None recorded.
