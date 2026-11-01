# State

_Updated 2026-11-01_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`). 833 tests.
- `parliament mcp` (#9, optional `[mcp]` extra, `mcp>=2.3,<3`): stdio server, one blocking `debate`
  tool. Returns `schema`, `summary` (contested, positions, warnings, degraded), `verdict`, `members`,
  `hansard_path` (~5 KB); the full Hansard (~60 KB) is saved as JSON under `~/.parliament/hansards/`.
  Progress per member answer, a heartbeat while queued, one debate at a time. README section
  "Use it from a coding agent (MCP)" has the client snippets; none tried in a real client yet.
- The Speaker ends with `CONTESTED:` / `ON WHAT:`, parsed into `Synthesis.contested`
  (`bool | None`) and `contested_on`. Correct on all 5 live debates of 2026-11-01.
- Self-reported positions, family tier rules, outside Speaker: all checked live 2026-11-01
  (Opus 5.5, GPT-5.1, Gemini 3.1 Pro; Grok 4.7 Speaker). Results in `docs/live-test-windows.md`.
- What the evidence supports: the debate catches a member's factual error and reports a real
  split; it does not give a more correct letter than one model on contested questions.

## Next
1. Merge #91 (Speaker model in the Hansard) before #92: they conflict in CHANGELOG and the
   Synthesis table of `docs/hansard-schema.md`; keep both sets of rows. #90 is docs only.
2. Try each README client snippet (Claude Code, Cursor, Codex) for real, then release 0.3.0
   (`RELEASING.md`) and drop the README "Not released yet" note.
3. A known-answer test: questions where one model tends to be wrong; count how often the panel
   corrects it. Fix the risk list before the run and grade blind.
4. Draft the #15/#8 comment (OpenRouter shipped, MCP is the chosen fork) for the owner to check.
5. #67 remainder, each its own PR: per-member `tier:` override, then Ollama size metadata.
6. Later: report an unrated outside Speaker (noted on #89); see panel warnings live; indent
   wrapped warning lines in the TUI.

## Decisions
- Positions are self-reported, never inferred; a missing answer is `null` (#73). The Speaker
  decides `contested`; `null` when it gives no line.
- The Speaker must not judge a position it holds; use an outside Speaker (#73, #79).
- Unrated models are reported, never silently excluded (#66, #67). Family rules match whole ids.
- MCP returns a trimmed result plus a saved file: the members' answers exceed client tool-output
  limits. Debates are serialised: OpenRouter reserves credit per request in flight (HTTP 402).
  Codex needs `tool_timeout_sec = 600`; the Cursor CLI (fixed 60 s) is unsupported.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- The 2026-09-04 comment on #9 carries an AI footer; editing it is the owner's call.
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`. pipx (uv backend) can't
  `--force` over an install: uninstall, then install.
- Cloud containers: system ruff 0.16.x flags a false DTZ005 and `python -m mypy` trips on numpy
  stubs; use a scratch-venv ruff and `~/.local/bin/mypy`. Cloud git defaults to the Claude
  identity: commit with `git -c user.name="Boris Miscenco" -c user.email=aidevblock@gmail.com`.
- Merging needs an approving review; fork PR CI waits for owner approval.
- Owner's PC, as of 2026-11-01: pipx runs editable from worktree `../llm-parliament-mcp`
  (`chore/local-mcp`) until the MCP PRs merge; Claude Code has `parliament` at user scope, and
  each call spends OpenRouter credit.
