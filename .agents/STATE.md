# State

_Updated 2026-10-11_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`).
- PR #86 (#69, branch `ccr-f5da835b-ki1dt2`, CI green, not merged): members self-report
  `POSITION:` (First Reading) plus `CHANGED MIND: yes/no` (Debate); `procedures/positions.py`
  reads only the answer's last 6 non-blank lines into `Response.position`, in `--json` and
  `docs/hansard-schema.md`. Chosen over a Speaker-written list: the Speaker sees no First
  Readings and is the biased party in #73. verify.sh green on the branch.
- Speaker neutrality (#73): Division anonymises members (`Member 1..n`, restored after
  parsing); optional outside Speaker `parliament.speaker`; a member takes over if it fails;
  `--speaker` still wins. `parliament ask` warns (`check_speaker`) on a shared model or a tie.
  The TUI shows neither these nor the tier warnings.
- `docs/live-test-windows.md`: eight debates on a contested question (Sonnet 5.5, GPT-5.6 Sol,
  Gemini 3.1 Pro; Grok 4.7 outside Speaker) gave B 6 times, A twice, but always the same first
  step and switch conditions. Outside judges agreed on 7 of 8; a same-model judge sided with
  its twin. README: "When it helps — measured", "Choosing the Speaker".

## Next
1. #86: merge, then one live debate to check models follow the trailer (hide it from display?
   show positions in the Markdown Hansard?). New prompts: not comparable with earlier runs.
2. MCP (#9) prerequisites: put gap/Speaker warnings into Hansard JSON; settle #9's return
   shape (flags only, per #15). Then the server.
3. Second contested question (analytics database) to see if "stable procedure, unstable
   letter" generalises. One debate at a time; OpenRouter balance ~$4.60 on 2026-10-10.
4. Live test step 5 and Windows checks (TUI, `Ctrl-C`, saved Hansard); record in the doc.
5. Unfiled: with `parliament.speaker` set, the unrated warning still says "Speaker selection
   assumes tier 3".
6. #56 follow-ups: AGENTS.md row **C** "not the matrix" is stale; derive
   `presets._cloud_openrouter_preset` ids from `GPT_4O_MINI` / `GEMINI_FLASH`.
7. #67: per-member `tier:` override; Ollama size; family rules. #66 leftover:
   `Member.base_url` vs `tier_base_url` alias.
8. #8: only #37 left; asked `kun-ren` 2026-10-11, no answer yet. Roadmap: #15.

## Decisions
- Agents read `AGENTS.md` directly; agent state lives in `.agents/` (not in the sdist).
- `scripts/verify.sh` mirrors ci.yml; `tests/test_verify_matches_ci.py` keeps them equal.
- The Speaker must not judge a position it holds (#73); Division input is always anonymised,
  insider Speakers are warned about (#79). Anonymising alone is not enough.
- Positions are self-reported, never inferred by the Speaker (#69); a missing answer is `null`.
- Unrated models are reported, never silently excluded (#66); tier 3 is an assumption.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- Cloud containers: both `~/.local/bin` (0.16.8) and `/usr/local/bin` (0.16.10) ruff are
  stale and flag a false DTZ005 on `tui.py`; CI runs the newest (0.17.0). Install ruff into a
  scratch venv. `python -m mypy` fails on system numpy stubs; `~/.local/bin/mypy` passes.
- `MODEL_TIERS` stops at Claude 4.6 / `gpt-4o`, so current models are unrated (#67).
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com`.
- `claude/community-engagement-improvements-abuakf` (personas, July) kept unmerged; decide.
- CI on fork PRs waits for owner approval; merging needs an approving review.
