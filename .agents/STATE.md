<!-- Hand-off between sessions on any machine, local or cloud. AGENTS.md imports it, so every
     session starts with it. The hand-off rewrites it; it is not a log, and history belongs in git.
     Keep it under ~40 lines; the SessionStart hook warns past 60. -->
# State

_Updated 2026-10-05_

## Now
- `main` (1dd283f) is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`).
- PR #65 (`fix/openrouter-tier-resolution`) is open for the tier part of issue #37: OpenRouter ids
  fold onto `MODEL_TIERS` for the lookup only, and unplaced OpenRouter models stay out of gap
  warnings. verify.sh was green locally; CI not yet checked. It replaces #64 (Kun Ren), closed
  2026-10-05 after no update since the 2026-09-26 review.
- PR #51 (`docs/escalation-gate-plan`) is waiting for review.

## Next
1. Check CI on #65, then review and merge it.
2. Review PR #51.
3. OpenRouter series: the #37 shortlist and free-model tier entries (not in #65), then #39
   (docs and doctor).
4. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly, so CLAUDE.md is gone and
  agent state lives under neutral names in `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.
- #65 scopes the "unplaced model" gap exclusion to OpenRouter; other providers still count their
  default tier 3.

## Known issues
- #65 leaves two gaps from the #64 review: `provider: openai` with an OpenRouter `base_url` gets
  no id folding, and unplaced OpenRouter models still rank as tier 3 for Speaker selection.
- On Windows, `bash scripts/verify.sh` picks the system `python` over the repo `.venv` and
  reports "dev dependencies missing". Workaround: `PATH="$PWD/.venv/Scripts:$PATH" bash
  scripts/verify.sh`, or activate the venv first.
