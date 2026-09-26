<!-- Hand-off between sessions on any machine, local or cloud. AGENTS.md imports it, so every
     session starts with it. The hand-off rewrites it; it is not a log, and history belongs in git.
     Keep it under ~40 lines; the SessionStart hook warns past 60. -->
# State

_Updated 2026-09-26_

## Now
- `main` (c2deab1) is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh is
  green: ruff and mypy clean, 553 tests.
- PR #64 (Kun Ren, for issue #37, OpenRouter tier resolution) is under review: **changes
  requested** on 2026-09-26. Inline review: pullrequestreview-5327639924. Blocking:
  1. OpenRouter IDs with version or instruct suffixes (`-001`, `-instruct`, `-it`) still miss
     `MODEL_TIERS`.
  2. `detect_gap` now ignores unknown models for every provider, not only OpenRouter.
  3. The PR rewrites `.agents/STATE.md` and adds a stale draft plan doc; both should be dropped.
- PR #51 (`docs/escalation-gate-plan`) is waiting for review.

## Next
1. When #64 is updated, re-review against the three blocking points above and the non-blocking
   ones in the inline review (Speaker vs. gap check on unknown models, `docs/configuration.md`
   lines 66 and 189, duplicated known-member filter in `check_gaps`).
2. Review PR #51.
3. OpenRouter series: #37 (catalog presets, via #64), then #39 (docs and doctor).
4. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly, so CLAUDE.md is gone and
  agent state lives under neutral names in `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.

## Known issues
- On Windows, `bash scripts/verify.sh` picks the system `python` over the repo `.venv` and
  reports "dev dependencies missing". Workaround: `PATH="$PWD/.venv/Scripts:$PATH" bash
  scripts/verify.sh`, or activate the venv first.
- The remote branch `origin/chore/agent-workflow` still exists although #63 merged it.
