<!-- Hand-off between sessions on any machine, local or cloud. AGENTS.md imports it, so every
     session starts with it. The hand-off rewrites it; it is not a log, and history belongs in git.
     Keep it under ~40 lines; the SessionStart hook warns past 60. -->
# State

_Updated 2026-10-05_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh is green.
- OpenRouter tiers (the tier part of #37): `get_tier(model, provider)` folds OpenRouter ids onto
  `MODEL_TIERS` for the lookup only (`core/model_tiers.py::canonical_model_id`), so frontier
  models can be Speaker and trigger gap warnings. Configured and API ids are never rewritten.
  An unplaced OpenRouter model keeps tier 3 but stays out of gap warnings.

## Next
1. Review PR #51 (`docs/escalation-gate-plan`).
2. OpenRouter series: the #37 shortlist and free-model tier entries, then #39 (docs and
   doctor). Recheck availability and pricing of any model before listing it.
3. Close the two tier gaps below if they matter.
4. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly, so CLAUDE.md is gone and
  agent state lives under neutral names in `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.
- The "unplaced model" gap exclusion is scoped to OpenRouter, where unlisted ids are routine.
  Other providers still count their default tier 3, so their warnings are unchanged.

## Known issues
- `provider: openai` with an OpenRouter `base_url` gets no id folding (`get_tier` sees only the
  provider name), and unplaced OpenRouter models still rank as tier 3 for Speaker selection.
- Commits made in cloud sessions can show a different author than the configured identity;
  check `git log -1 --format='%an <%ae>'` before pushing.
- On Windows, `bash scripts/verify.sh` picks the system `python` over the repo `.venv` and
  reports "dev dependencies missing". Workaround: `PATH="$PWD/.venv/Scripts:$PATH" bash
  scripts/verify.sh`, or activate the venv first.
- The remote branch `origin/chore/agent-workflow` still exists although #63 merged it.
