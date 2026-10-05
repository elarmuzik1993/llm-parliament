# State

_Updated 2026-10-05_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh is green.
- OpenRouter tiers (the tier part of #37): `get_tier(model, provider)` folds OpenRouter ids onto
  `MODEL_TIERS` for the lookup only (`core/model_tiers.py::canonical_model_id`). An id listed
  as-is wins before suffix folding. Configured and API ids are never rewritten. An unplaced
  OpenRouter model keeps tier 3 but stays out of gap warnings.
- First-run wizard offers a `cloud-openrouter` preset (#56) when `OPENROUTER_API_KEY` is set.

## Next
1. Review PR #51 (`docs/escalation-gate-plan`), a validation plan doc, one file.
2. Small follow-ups from the #56 review:
   - AGENTS.md row **C**: `tests/test_first_run_presets.py` now covers the full key x router x
     local matrix, so "not the matrix" is stale.
   - `presets._cloud_openrouter_preset` hardcodes its ids; derive `openai/` and `google/` ones
     from `GPT_4O_MINI` / `GEMINI_FLASH` so they follow the direct presets.
3. OpenRouter series: the #37 shortlist and free-model tier entries, then #39 (docs and
   doctor). Recheck availability and pricing of any model before listing it.
4. Close the tier gaps below if they matter.
5. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly; agent state lives in
  `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.
- The "unplaced model" gap exclusion is scoped to OpenRouter, where unlisted ids are routine.
  Other providers still count their default tier 3, so their warnings are unchanged.

## Known issues
- Tier gaps: `provider: openai` with an OpenRouter `base_url` gets no folding; unplaced
  OpenRouter models rank as tier 3 for Speaker selection; dated ids (`gpt-4o-2024-11-20`,
  `mistral-large-2411`) and stacked suffixes (`-instruct-001`) stay unplaced.
- Cloud sessions default git to `Claude <noreply@anthropic.com>`. Commit with
  `git -c user.name="Boris Miscenco" -c user.email=...` and check `git log -1 --format='%an <%ae>'`.
- On Windows, `bash scripts/verify.sh` picks the system `python` over the repo `.venv` and
  reports "dev dependencies missing". Workaround: `PATH="$PWD/.venv/Scripts:$PATH" bash
  scripts/verify.sh`, or activate the venv first.
- Stale remote branches: `chore/agent-workflow`, `fix/openrouter-tier-resolution`, and three
  `claude/...` branches. Delete once confirmed unneeded.
