# State

_Updated 2026-10-06_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`).
- #66 (kun-ren) is merged. `provider: openai` at a registered OpenAI-compatible endpoint (matched
  strictly via `OPENAI_COMPATIBLE`) rates like that provider. `calculate_gap()` returns a
  `TierAssessment` (`gap`, `unrated_members`, `rated_count`, `comparable`); a gap and unrated
  members can both be set. Unrated real models, for every provider, are reported ("unrated,
  assumed tier 3") in the CLI, TUI and saved Markdown, and as `unrated_members` in the Hansard JSON
  (`docs/hansard-schema.md`, checked against the dataclass fields). Mock tiers are synthetic and
  never flagged. `Member.base_url` is runtime-only and not serialized.
- First-run wizard offers a `cloud-openrouter` preset (#56) when `OPENROUTER_API_KEY` is set.

## Next
1. Review #51 (`docs/escalation-gate-plan`, one doc file; base behind `main`).
2. #56 follow-ups: AGENTS.md row **C** says "not the matrix", now stale; derive
   `presets._cloud_openrouter_preset` ids from `GPT_4O_MINI` / `GEMINI_FLASH`.
3. #67, what is left, in order: per-member `tier:` override; Ollama size as a source; family
   rules last. Settle its open questions first.
4. Small #66 leftovers: `Member.base_url` and its `tier_base_url` alias are one value under two
   names, drop one. For MCP (#9), the rated-gap result is not in the Hansard JSON, only
   `unrated_members` is.
5. OpenRouter series: #37 shortlist and free-model tiers, then #39. Roadmap: #15.

## Decisions
- Agents read `AGENTS.md` directly; agent state lives in `.agents/` (not in the sdist).
- `scripts/verify.sh` mirrors ci.yml; `tests/test_verify_matches_ci.py` keeps them equal.
- Unrated models are excluded from the rated-gap comparison for every provider (#66, replacing
  #65's OpenRouter-only scope), but never silently: they are reported, so "no gap" cannot hide
  unrated members. Fallback tier 3 stays a Speaker-selection assumption, not a rating. The tool
  raises flags and never clears them (MCP mode #9).
- OpenRouter suffix folding was replaced by explicit `MODEL_ALIASES` entries (#66); an id that no
  longer folds shows as unrated.
- No live leaderboard feed, no price as a capability proxy.

## Known issues
- `MODEL_TIERS` stops at the 4.6 Claude models and `gpt-4o`, so newer models are unrated and rank
  as tier 3 for Speaker selection (#67). Dated ids and stacked suffixes stay unplaced.
- In cloud containers verify.sh's `python -m mypy` fails on numpy's system stub (`type`
  statement); `mypy src/parliament` passes. Ruff and pytest pass.
- On Windows, verify.sh picks the system `python`: prefix `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com` and check `git log -1 --format='%an <%ae>'`.
- Stale remote branches: `chore/agent-workflow`, `fix/openrouter-tier-resolution`, three
  `claude/...` ones. Delete once confirmed unneeded.
