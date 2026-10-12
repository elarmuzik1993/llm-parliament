# State

_Updated 2026-10-12_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). 806 tests.
- Members self-report positions (#69): a `POSITION:` line, plus `CHANGED MIND: yes/no` in Debate,
  parsed into `Response.position` (`null` when absent). Not yet seen with real models.
- Speaker neutrality (#73): anonymised Division input; optional outside Speaker
  (`parliament.speaker`).
- Panel warnings (`tier_gap`, `unrated`, `speaker`) come from one function,
  `core/parliament.py::panel_warnings()`, which needs no provider clients. `ask` prints them,
  `members` prints them, and the Hansard records them as `warnings: [{kind, message}]`
  (schema doc updated). The TUI and saved `.md` list them one line each below the Recommendation.
- Tiers (#67): `MODEL_TIERS`, then `FAMILY_RULES` (Claude 4+, GPT-5+, Gemini 2+, whole-id matches,
  labelled `(inferred)`), else unrated. Automatic Speaker selection picks from rated members
  first. Still unrated: xAI, DeepSeek, Qwen, o-series, Claude Fable, fine-tunes, dated snapshots.
- OpenRouter works end to end. #37 (curated shortlist) is polish.

## Next
1. One live OpenRouter debate (Opus 5.5 / GPT-5.1 / Gemini 3 Pro): do members emit the
   `POSITION:` trailer, do the family rules rate them, how do the warnings read on screen?
   New prompts make these runs not comparable with `docs/live-test-windows.md`.
2. Record on #15 (and #8) that OpenRouter counts as shipped and MCP (#9) is the chosen fork;
   draft the comment for the owner to check before posting.
3. Settle #9's return shape with the owner: full Hansard (warnings included) plus a flat
   "contested / on what" summary, flags only. Then `parliament mcp`, one `debate` tool.
4. #67 remainder, each its own PR: per-member `tier:` override (reverses "tier is not
   configurable" in `docs/configuration.md`), then Ollama size metadata.
5. Later: indent wrapped warning lines in the TUI; second contested question; Windows live checks.

## Decisions
- Positions are self-reported, never inferred by the Speaker; a missing answer is `null` (#73).
- The Speaker must not judge a position it holds; anonymising alone is not enough (#73, #79).
- Unrated models are reported, never silently excluded (#66); tier 3 is an assumption, so an
  unrated member becomes Speaker only when no member is rated (#67).
- Family rules match the whole id: a wrong rating is worse than "unrated". Pin exceptions
  (e.g. a preset's dated id) in `MODEL_TIERS`; tests fail when the two disagree.
- Warnings describe the configured panel, taken before the debate. Filter on `kind`, never on
  wording. On screen only each message's first sentence shows; the advice stays in JSON/stderr.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- Cloud containers: `verify.sh` fails on env only. System ruff (0.16.x) flags a false DTZ005
  on `tui.py` (CI runs 0.17.0), and `python -m mypy` trips on numpy stubs. Run ruff from a
  scratch venv with the newest ruff, `~/.local/bin/mypy src/parliament`, `python -m pytest -q`.
- A tied top tier still raises the Speaker warning on most real panels; `parliament.speaker`
  with a model off the panel clears it. That is intended (#73).
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`.
- Cloud git defaults to the Claude identity: commit with `git -c user.name="Boris Miscenco"
  -c user.email=aidevblock@gmail.com`.
- Merging needs an approving review; fork PR CI waits for owner approval.
