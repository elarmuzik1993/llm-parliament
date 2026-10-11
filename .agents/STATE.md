# State

_Updated 2026-10-11 (#69 branch)_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). verify.sh green: 736 tests.
- Speaker neutrality (#73): the Division prompt anonymises members (`Member 1..n`, names
  scrubbed from the text, restored after parsing), and an optional `parliament.speaker`
  (provider/model/name) is an outside Speaker that did not debate. If it fails, a member takes
  over; `--speaker <member>` still wins. `parliament ask` warns (`Parliament.check_speaker`)
  when the outside Speaker shares a member's model, or when tied members leave the Speaker to
  be picked by order. The TUI shows neither these nor the tier warnings.
- `docs/live-test-windows.md` holds the Windows/OpenRouter live test plan and four result sets.
  Headline: on a contested question, eight debates (Sonnet 5.5, GPT-5.6 Sol, Gemini 3.1 Pro;
  Grok 4.7 as outside Speaker) gave B 6 times and A twice, but always the same first step and
  switch conditions, where single calls change their answer with the wording. Re-judging the
  same debates, outside judges agreed on 7 of 8; a judge sharing a member's model sided with it.
  The README summarises this under "When it helps — measured" and "Choosing the Speaker".

- #69 in progress on branch `ccr-f5da835b-ki1dt2` (not merged): members self-report a
  `POSITION:` line (First Reading) plus `CHANGED MIND: yes/no` (Debate), parsed by
  `procedures/positions.py` into `Response.position`; in `--json` and `docs/hansard-schema.md`,
  whose Response/Position/Synthesis tables are now pinned by `test_docs_match_code.py`.
  Chosen over a Speaker-written POSITIONS section: the Speaker sees no First Readings and is
  the biased party in #73. 752 tests.

## Next
0. #69: open the PR, then a live run to see how real models follow the trailer (strip it from
   displayed content? render positions in the Hansard markdown?). Then the MCP prerequisites:
   check warnings (gap, Speaker) into Hansard JSON, then #9's return shape.
1. Test a second contested question to see if "stable procedure, unstable letter" generalises.
   The analytics-database question in the doc's screen is the next candidate. Run debates
   **one at a time**; check the OpenRouter balance first (about $4.60 on 2026-10-10).
2. Live test step 5 and the Windows checks (TUI rendering, `Ctrl-C`, saved Hansard), using the
   same config; record them in the doc.
3. Small follow-up, not filed yet: with `parliament.speaker` set, the unrated-members warning
   still says "Speaker selection assumes tier 3".
4. #56 follow-ups: AGENTS.md row **C** says "not the matrix", now stale; derive
   `presets._cloud_openrouter_preset` ids from `GPT_4O_MINI` / `GEMINI_FLASH`.
5. #67 in order: per-member `tier:` override; Ollama size; family rules. #66 leftovers:
   `Member.base_url` vs `tier_base_url` alias; rated gap missing from Hansard JSON (MCP, #9).
6. OpenRouter series (#8): only #37 is left (curated shortlist; tiers done in #65/#66). Asked
   `kun-ren` on 2026-10-11 whether they are still on it; no answer yet. Roadmap: #15.

## Decisions
- Agents read `AGENTS.md` directly; agent state lives in `.agents/` (not in the sdist).
- `scripts/verify.sh` mirrors ci.yml; `tests/test_verify_matches_ci.py` keeps them equal.
- The Speaker must not judge a position it holds (#73). Division input is always anonymised;
  an outside Speaker is opt-in, so existing configs behave as before, but insider Speakers
  are warned about (#79). Anonymising alone is not enough: a same-model judge still sided with
  its twin in the judge swap.
- Unrated models are reported, never silently excluded (#66); fallback tier 3 is a
  Speaker-selection assumption, not a rating. No live leaderboard feed, no price as a proxy.
- Ruff is unpinned on purpose (`pyproject.toml`): a new ruff release can fail CI on old code;
  fix the finding rather than pin.

## Known issues
- Local ruff can lag CI's: CI installs the newest version (0.17.0 on 2026-10-10). In cloud
  containers both `~/.local/bin` (0.16.8) and `/usr/local/bin` (0.16.10) ruff are stale and
  report a false DTZ005 on `tui.py`; install the newest ruff into a scratch venv and run that. There, `python -m mypy` then fails on
  the system numpy stubs (needs 3.12); `~/.local/bin/mypy src/parliament` passes. Env-only.
- `MODEL_TIERS` stops at Claude 4.6 / `gpt-4o`, so current models are unrated (#67).
- On Windows, verify.sh picks the system `python`: prefix `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com`.
- `claude/community-engagement-improvements-abuakf` (member personas, 2 commits from July) is
  kept on the remote on purpose, unmerged and without a PR. Decide: revive or delete.
- CI on fork PRs waits for the owner to approve the run; merging needs an approving review.
