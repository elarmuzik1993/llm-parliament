# State

_Updated 2026-11-03_

## Now
- `main` is 0.2.0 plus unreleased changes (CHANGELOG `[Unreleased]`), through #102. 865 tests.
- `parliament mcp` (#9, optional `[mcp]` extra) is a ladder of three tools (#99):
  - `ask(member, question)`: one call to one panel member or the outside Speaker. No lock; record
    in `~/.parliament/hansards/asks/`.
  - `consult(question, members?)`: First Reading alone, 2+ panel members in parallel, self-reported
    stances, no Speaker, no `contested`. Takes the debate lock; answers capped at 8,000 chars in the
    result; record in `hansards/consults/`.
  - `debate(question)`: unchanged. Returns `summary`, `verdict`, `members`, `hansard_path`.
- `OpenAIProvider` caps output at 16,384 tokens (`max_completion_tokens` on api.openai.com,
  `max_tokens` elsewhere); an empty reply raises. Meant to stop OpenRouter's 65,536-token credit
  reservation causing 402s: unverified live.
- `ask` and `consult` are tested only against mock providers; no live run yet.
- Owner's setup: pipx build from the main checkout (reinstall after pulling); panel Grok 4.7,
  GPT-6.1 Sol Pro, Gemini 4 Argon, all unrated; outside Speaker Opus 5.5. A debate costs ~$0.4-0.5.
- Evidence so far: the debate catches a member's factual error, reports a real split and gathers
  risks; it does not give a more correct letter than one model on contested questions.

## Next
1. Live-test from Claude Code on the owner's machine, once OpenRouter has credit and a new key:
   one `ask`, one `consult`, one `debate`; check no 402, and that records match the results.
   Note findings in `docs/live-test-windows.md`.
2. Flag (a `speaker` warning) or fail when a debater becomes Speaker after the outside Speaker fails.
3. Cost and tokens in all three tool results (#70); the saved records are where they go.
4. `ask(..., hansard_path=...)`: follow up on a saved debate (e.g. ask the dissenter) (#99).
5. Rate the models in use, so the `unrated` warning stops repeating every run.
6. A known-answer test: one model's errors, panel vs single-model baseline, risks fixed first,
   graded blind.
7. Try the README client snippets in Cursor and Codex, then release 0.3.0 (`RELEASING.md`).
8. #67 remainder, each its own PR: per-member `tier:` override, then Ollama size metadata.

## Decisions
- Positions are self-reported, never inferred; a missing answer is `null` (#73). Only the Speaker
  decides `contested`, so `consult` has none.
- The Speaker must not judge a position it holds; use an outside Speaker (#73, #79).
- Unrated models are reported, never silently excluded (#66, #67).
- MCP returns trimmed results plus a saved file (client output limits). Fan-outs (`debate`,
  `consult`) are serialised for OpenRouter credit; `ask` is not. Codex needs `tool_timeout_sec = 600`.
- The output cap is one constant, not config; 16k because reasoning tokens count against it.
- Ruff is unpinned on purpose: fix a new release's finding rather than pin.

## Known issues
- When the outside Speaker fails, a debater writes the verdict and nothing flags it (Next 2).
- OpenRouter: about $0.92 credit left (2026-11-02) and the key expires 2026-11-03 ~20:04 UTC; `parliament keys set openrouter <key>`. No provider keys exist in cloud containers.
- Windows: prefix verify.sh with `PATH="$PWD/.venv/Scripts:$PATH"`. pipx (uv backend) can't
  `--force` over an install: uninstall, then install.
- Cloud containers: verify.sh's mypy fails on numpy stubs; run `~/.local/bin/mypy src/parliament`.
  Bare `ruff` is 0.16.x with a false DTZ005; use `python -m ruff`. Worktree subagents start from a
  stale local `main`: reset them to `origin/...` first. Commit with
  `git -c user.name="Boris Miscenco" -c user.email=aidevblock@gmail.com`.
- The GitHub connector appends an AI footer to PR bodies; strip it by updating the body.
- The connector's merge goes through while a PR reads `blocked` and CI is still running: check
  that CI is green first. Fork PR CI waits for owner approval.
