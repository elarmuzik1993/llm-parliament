# State

_Updated 2026-11-02_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`), through #96. 838 tests.
- `parliament mcp` (#9, optional `[mcp]` extra): stdio server, one blocking `debate` tool. Returns
  `summary` (contested, positions, warnings, degraded), `verdict`, `members`, `hansard_path`; the
  full Hansard is saved under `~/.parliament/hansards/`. Used for three real decisions on
  2026-11-02 from Claude Code (user scope), the 2nd and 3rd with a full panel; results, bias check
  and cost in `docs/live-test-windows.md`. Cursor and Codex untried.
- A member lost in First Reading or Debate, or a Speaker replaced in Division, leaves a
  `member_failed` warning with the provider error (#95). Seen working live on the third debate.
- Owner's setup: pipx build installed from the main checkout after #96 (reinstall after pulling);
  panel Grok 4.7, GPT-6.1 Sol Pro, Gemini 4 Argon, all unrated; outside Speaker Opus 5.5; config in
  `~/.parliament/config.yaml`. A debate costs about $0.4-0.5 (from key usage; per-debate split unknown).
- What the evidence supports: the debate catches a member's factual error, reports a real split and
  gathers risks; it does not give a more correct letter than one model on contested questions.
  Owner's view: it helps distil better answers and adds reassurance. Agreement is not proof, and
  neither is one model's answer.

## Next
1. Polish the MCP tool, in this order, each its own PR:
   a. Flag (a `speaker` warning) or fail when a debater becomes Speaker after the outside Speaker fails.
   b. Cost and tokens in the result (#70).
   c. Cap the Speaker's `max_tokens` so OpenRouter's credit reservation (HTTP 402) cannot kill it.
   d. Rate the models in use, so the `unrated` warning stops repeating every run.
   e. A brief template in the tool description: context, options, numbered questions, constraints.
2. A known-answer test: questions where one model tends to be wrong; count how often the panel
   corrects it, against a single-model baseline. Fix the risk list before the run, grade blind.
3. Try each README client snippet (Claude Code done; Cursor, Codex) then release 0.3.0
   (`RELEASING.md`) and drop the README "Not released yet" note.
4. Draft the #15/#8 comment (OpenRouter shipped, MCP is the chosen fork) for the owner to check.
5. #67 remainder, each its own PR: per-member `tier:` override, then Ollama size metadata.

## Decisions
- Positions are self-reported, never inferred; a missing answer is `null` (#73). The Speaker
  decides `contested`; `null` when it gives no line.
- The Speaker must not judge a position it holds; use an outside Speaker (#73, #79).
- Unrated models are reported, never silently excluded (#66, #67). Family rules match whole ids.
- MCP returns a trimmed result plus a saved file: the members' answers exceed client tool-output
  limits. Debates are serialised. Codex needs `tool_timeout_sec = 600`; the Cursor CLI (fixed 60 s)
  is unsupported.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- When the outside Speaker fails, a debater writes the verdict (2026-11-02: Opus 5.5 hit a 402, Grok
  took over). The failure is recorded; nothing says the Speaker is now a participant. A bias check
  of that verdict against the members' answers found no sign of Grok favouring itself.
- OpenRouter 402s come from the 65,536-token output reservation exceeding remaining credit, not from
  the debate's size. As of 2026-11-02 the account had about $0.92 credit left and the key expires
  2026-11-03 about 20:04 UTC: add credit and a new key (`parliament keys set openrouter <key>`).
- GPT-6 Astra dropped out silently in the first real debate; cause unknown (no error was kept then).
- The 2026-09-04 comment on #9 carries an AI footer; editing it is the owner's call.
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`. pipx (uv backend) can't
  `--force` over an install: uninstall, then install.
- Cloud containers: system ruff 0.16.x flags a false DTZ005 and `python -m mypy` trips on numpy
  stubs; use a scratch-venv ruff and `~/.local/bin/mypy`. Cloud git defaults to the Claude
  identity: commit with `git -c user.name="Boris Miscenco" -c user.email=aidevblock@gmail.com`.
- Merging needs an approving review; fork PR CI waits for owner approval.
