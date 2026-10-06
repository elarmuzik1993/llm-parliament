# State

_Updated 2026-10-06_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`).
- OpenRouter tiers (#37, tier part): `core/model_tiers.py::canonical_model_id` folds OpenRouter ids
  onto `MODEL_TIERS` for lookup only; API ids are never rewritten. An unplaced OpenRouter model
  keeps tier 3 but stays out of gap warnings.
- First-run wizard offers a `cloud-openrouter` preset (#56) when `OPENROUTER_API_KEY` is set.
- #66 (kun-ren, endpoint-aware tiers) has the revised owner review. At head `80afc06`: pytest
  passes, mypy clean, ruff fails on `ISC004` (`tests/test_parliament.py:212`); opus-4-6 plus an
  unrated Ollama model returns no gap, which is the blocking point. #67 tracks the tier rework.

## Next
1. The revised #66 comment lost its Markdown when pasted (no code spans, list or paragraphs).
   Re-edit it in GitHub's Markdown tab if it should read cleanly.
2. On a new #66 push: check `ISC004`, the three-state gap result or the dropped all-provider
   exclusion, then merge the endpoint work and update the exclusion decision below.
3. Review #51 (`docs/escalation-gate-plan`, one doc file; base behind `main`).
4. #56 follow-ups: AGENTS.md row **C** says "not the matrix", now stale; derive
   `presets._cloud_openrouter_preset` ids from `GPT_4O_MINI` / `GEMINI_FLASH`.
5. #67 in order: three-state gap + `unrated_members` in Hansard JSON and `docs/hansard-schema.md`;
   per-member `tier:` override; Ollama size as a source; family rules last.
6. OpenRouter series: #37 shortlist and free-model tiers, then #39. Roadmap: #15.

## Decisions
- Agents read `AGENTS.md` directly; agent state lives in `.agents/` (not in the sdist).
- `scripts/verify.sh` mirrors ci.yml; `tests/test_verify_matches_ci.py` keeps them equal.
- Unplaced-model gap exclusion stays OpenRouter-only until unrated members are reported openly.
  The tool raises flags and never clears them (MCP mode #9): "no gap" must not hide unrated ones.
- Explicit aliases instead of suffix folding (#66) are accepted on that same condition.
- No live leaderboard feed, no price as a capability proxy.

## Known issues
- Tier gaps: `provider: openai` with an OpenRouter `base_url` gets no folding (#66 fixes it);
  dated ids and stacked suffixes stay unplaced.
- In cloud containers verify.sh's `python -m mypy` fails on numpy's system stub (`type`
  statement); `mypy src/parliament` passes. Ruff and pytest pass.
- On Windows, verify.sh picks the system `python`: prefix `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com` and check `git log -1 --format='%an <%ae>'`.
- Stale remote branches: `chore/agent-workflow`, `fix/openrouter-tier-resolution`, three
  `claude/...` ones. Delete once confirmed unneeded.
