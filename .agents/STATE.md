# State

_Updated 2026-10-11_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). 759 tests.
- Members self-report positions (#69): `POSITION:` after First Reading, plus `CHANGED MIND:
  yes/no` after Debate. `procedures/positions.py` reads only an answer's last 6 non-blank lines
  into `Response.position` (`null` when absent); in `--json` and `docs/hansard-schema.md`.
  Not yet seen with real models.
- Speaker neutrality (#73): Division input is anonymised; optional outside Speaker
  (`parliament.speaker`); `parliament ask` warns on insider Speakers. The TUI shows neither
  these nor the tier warnings, and neither warning reaches Hansard JSON.
- OpenRouter works end to end (provider, keys, wizard, docs). #37 (curated model shortlist,
  `kun-ren`) is polish, not a blocker.

## Next
1. One live OpenRouter debate: do all members emit the trailer, does it parse, does it
   clutter the display? Adjust the prompt wording if a model ignores it. New prompts make
   these runs not comparable with `docs/live-test-windows.md`.
2. Record on #15 (and #8) that OpenRouter counts as shipped and MCP (#9) is the chosen fork;
   draft the comment for the owner to check before posting.
3. Gap and Speaker warnings (`check_gaps`, `check_speaker`) into Hansard JSON + schema doc.
4. Settle #9's return shape with the owner: full Hansard plus a flat "contested / on what"
   summary, flags only (#15), agent decides when to call. Then `parliament mcp`, one `debate`
   tool, `mcp` as an optional extra.
5. Later: second contested question (OpenRouter ~$4.60 on 2026-10-10); Windows live checks;
   unrated warning wording with an outside Speaker; #56 and #67 follow-ups.

## Decisions
- Positions are self-reported, never inferred by the Speaker: it sees no First Readings and
  is the biased party (#73). A missing answer is `null`, never guessed.
- The Speaker must not judge a position it holds; anonymising alone is not enough (#73, #79).
- Unrated models are reported, never silently excluded (#66); tier 3 is an assumption.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- Cloud containers: `verify.sh` fails on env only. System ruff (0.16.x) flags a false DTZ005
  on `tui.py` (CI runs 0.17.0), and `python -m mypy` trips on numpy stubs. Run ruff from a
  scratch venv with the newest ruff, `~/.local/bin/mypy src/parliament`, `python -m pytest -q`.
- `MODEL_TIERS` stops at Claude 4.6 / `gpt-4o`, so current models are unrated (#67).
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com`.
- Merging needs an approving review; fork PR CI waits for owner approval.
