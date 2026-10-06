# State

_Updated 2026-10-06_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh is green.
- OpenRouter tiers (the tier part of #37): `get_tier(model, provider)` folds OpenRouter ids onto
  `MODEL_TIERS` for the lookup only (`core/model_tiers.py::canonical_model_id`). An id listed
  as-is wins before suffix folding. Configured and API ids are never rewritten. An unplaced
  OpenRouter model keeps tier 3 but stays out of gap warnings.
- First-run wizard offers a `cloud-openrouter` preset (#56) when `OPENROUTER_API_KEY` is set.
- PR #66 (kun-ren, endpoint-aware tiers) is open with a review comment asking for changes; waiting
  on the contributor. Its endpoint work is wanted. Its all-provider gap exclusion is not, as written.
- Design issue #67 tracks the tier-rating rework (see Decisions).

## Next
1. Follow up on PR #66: ruff `ISC004` at `tests/test_parliament.py:212` must be fixed; merge the
   endpoint work once the unrated-model handling is settled (three-state result below), or split it.
   Then update the gap-exclusion decision below to match what lands.
   Review PR #51 (`docs/escalation-gate-plan`), a validation plan doc, one file. Its base is
   behind `main`.
2. Small follow-ups from the #56 review:
   - AGENTS.md row **C**: `tests/test_first_run_presets.py` now covers the full key x router x
     local matrix, so "not the matrix" is stale.
   - `presets._cloud_openrouter_preset` hardcodes its ids; derive `openai/` and `google/` ones
     from `GPT_4O_MINI` / `GEMINI_FLASH` so they follow the direct presets.
3. #67, in order: three-state gap result plus `unrated_members` in the Hansard JSON (and
   `docs/hansard-schema.md`); a per-member `tier:` override; Ollama size as a rating source;
   family rules last. Settle the open questions in #67 first.
4. OpenRouter series: the #37 shortlist and free-model tier entries, then #39 (docs and
   doctor). Recheck availability and pricing of any model before listing it.
5. Close the tier gaps below if they matter; #67 covers most of them.
6. Roadmap and wider plans: #15.

## Decisions
- No per-tool agent files: coding agents read `AGENTS.md` directly; agent state lives in
  `.agents/` (excluded from the sdist, like AGENTS.md).
- `scripts/verify.sh` copies ci.yml's checks; `tests/test_verify_matches_ci.py` keeps them equal.
- The "unplaced model" gap exclusion is scoped to OpenRouter, where unlisted ids are routine.
  Other providers still count their default tier 3, so their warnings are unchanged. This is
  what `main` does today; #66 proposes extending it to every provider and is not accepted as is.
- Direction (from the #66 review, for MCP mode #9): the tool raises flags and never clears them.
  An unrated model must be reported, not dropped, so "no gap" never hides unrated members.
  `MODEL_TIERS` is small and already stale (it stops at the 4.6 Claude models and `gpt-4o`), so
  unrated is common. A live leaderboard feed and price-as-capability are ruled out.
- Suffix folding (`-instruct`, `-it`, `-NNN`) vs explicit aliases, as #66 proposes: acceptable
  only if unrated models are reported openly. Contributor asked to confirm it is deliberate.

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
