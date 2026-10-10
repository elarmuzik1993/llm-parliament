# State

_Updated 2026-10-10_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh green: 724 tests.
- Speaker neutrality (#73): the Division prompt anonymises members (`Member 1..n`, names
  scrubbed from the text, restored after parsing), and an optional `parliament.speaker`
  (provider/model/name) is an outside Speaker that did not debate. If it fails, a member takes
  over; `--speaker <member>` still wins.
- `docs/live-test-windows.md` holds the Windows/OpenRouter live test plan and three result sets.
  Headline: on the memory-safety question (Q5 there), single calls to Sonnet 5.5 / GPT-5.6 Sol /
  Gemini 3.1 Pro scatter across all three options. The parliament (those three, with Grok 4.7
  as outside Speaker) gave B in 3 of 3 valid runs, with the same conditions for switching. The
  original monolith question no longer divides frontier models.
- Contributor PRs are open for #72 (synthesis parser strips bold) and #74 (Windows encoding crash).

## Next
1. Review the #72 and #74 contributor PRs. The #72 one edits `procedures/division.py`, which the
   #73 fix also changed, so check it rebased and that `test_speaker_neutrality.py` still passes.
2. Finish Q5 stability: 2–5 more debates, run **one at a time**. Config: the members and Speaker
   named in the doc's "contested questions" section. Check the OpenRouter account balance first
   (about $1.70 left at the end of 2026-10-10).
3. Live test step 5 and the Windows checks (TUI rendering, `Ctrl-C`, saved Hansard), using the
   same config; record them in the doc.
4. Small follow-up, not filed yet: with `parliament.speaker` set, the unrated-members warning
   still says "Speaker selection assumes tier 3".
5. #56 follow-ups: AGENTS.md row **C** says "not the matrix", now stale; derive
   `presets._cloud_openrouter_preset` ids from `GPT_4O_MINI` / `GEMINI_FLASH`.
6. #67 in order: per-member `tier:` override; Ollama size; family rules. #66 leftovers:
   `Member.base_url` vs `tier_base_url` alias; rated gap missing from Hansard JSON (MCP, #9).
7. OpenRouter series: #37, then #39. Roadmap: #15.

## Decisions
- Agents read `AGENTS.md` directly; agent state lives in `.agents/` (not in the sdist).
- `scripts/verify.sh` mirrors ci.yml; `tests/test_verify_matches_ci.py` keeps them equal.
- The Speaker must not judge a position it holds (#73). Division input is always anonymised;
  an outside Speaker is opt-in, so existing configs behave as before.
- Unrated models are reported, never silently excluded (#66); fallback tier 3 is a
  Speaker-selection assumption, not a rating. No live leaderboard feed, no price as a proxy.
- Ruff is unpinned on purpose (`pyproject.toml`): a new ruff release can fail CI on old code;
  fix the finding rather than pin.

## Known issues
- Local ruff can lag CI's: CI installs the newest version (0.17.0 on 2026-10-10). Upgrade the
  venv's ruff before trusting a local green.
- Until #74 is fixed, `doctor` and plain `ask` crash on Windows when output is redirected; set
  `PYTHONIOENCODING=utf-8`. `ask --json` is unaffected.
- `MODEL_TIERS` stops at Claude 4.6 / `gpt-4o`, so current models are unrated (#67).
- On Windows, verify.sh picks the system `python`: prefix `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com`.
- Stale remote branches: `fix/openrouter-tier-resolution`, `chore/review-66-handoff`,
  `docs/state-after-66-review`, three `claude/...` ones. Delete once confirmed unneeded.
