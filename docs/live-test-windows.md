# Live test plan: Windows, OpenRouter

Goal: find out whether disagreement between members is useful, not just present.
About 30 minutes. Needs an OpenRouter key with a small credit limit.

## Choosing the question

A question every model agrees on shows nothing. A purely subjective one gives
noise. Use a forced choice between options that trade off differently, with
enough context that a wrong answer is defensible but costly, and run it next to
a control.

**Main question:**

> We are 6 engineers running a 40k-line Python monolith on one shared Postgres. We had 3 outages in 2 months, all from long queries blocking the checkout path. We have 6 weeks before a big launch. Choose exactly one: (A) split checkout into its own service with its own database, (B) keep the monolith and add read replicas plus pgbouncer, (C) freeze features for 4 weeks and fix the slow queries. Pick one, justify it, and say what would change your mind.

The options are different bets (architecture, infrastructure, process). The
deadline pushes some models toward caution and others toward the root cause.
"What would change your mind" makes the Risks section concrete.

**Control question (should produce consensus):**

> Should passwords be stored as salted hashes using bcrypt or argon2, or encrypted so they can be recovered?

If the parliament invents a split here, the disagreement is theater.

## Steps

1. Use Windows Terminal. Store the key with `parliament keys set openrouter <key>`
   in your own terminal; it takes the key only as an argument, so don't run it
   anywhere that records the command. Run `parliament doctor`; OpenRouter
   should show as configured. To keep an existing config, put the three members
   in a separate file and pass it with `--config`.
2. Baseline: ask one of the three models alone (a single-member config or the
   provider's own chat) with the main question. Save the answer.
3. Run `parliament ask --json "<main question>"` and save the output to a file.
4. Run the control question the same way.
5. Run the main question once in the TUI (`parliament`) to check the curses screens.
6. Repeat step 3 once. Compare the two runs for stability.

## Scoring: is the disagreement useful?

| Check | Pass looks like |
|---|---|
| First Reading positions | At least two different options chosen, or the same option for different reasons |
| Split section | Names who disagreed and why, not just "some prefer A" |
| Debate effect | At least one member changes or sharpens their position after critiques |
| Risks | Contains something the baseline answer did not mention |
| Speaker fairness | The minority view is represented as strongly as the majority |
| Control | Consensus, with no manufactured split |
| Stability | The second run reaches the same verdict, or the same split |
| Verdict vs baseline | You can state what the parliament told you that one model did not |

If the verdict is no better than the baseline and the split is vague, the
parliament is an expensive single call at this setup.

## Windows-specific checks

- Spinner and glyphs render in Windows Terminal.
- The live view does not freeze or flicker during the debate (threading model).
- `Ctrl-C` during a debate exits cleanly, with no fake verdict.
- Saving writes a readable `.md` to `%USERPROFILE%\.parliament\hansards\`.
- The Hansard is not marked `degraded`.

## Record per run

Wall time, rough cost from the OpenRouter dashboard, models used, and whether
any members dropped. Redact keys as `***` before sharing any output.

## Results: 2026-10-10

Windows 11, Python 3.14, `main` at `5d7c2d4`. The OpenRouter preset:
`anthropic/claude-sonnet-4.6`, `openai/gpt-4o-mini`, `google/gemini-2.5-flash`.
All three were rated tier 2 and none were unrated. The baseline is a single call
to Sonnet 4.6 with the bare question. Total cost for everything below: $0.27.

| Run | Wall | First Reading picks | Verdict | Degraded |
|---|---|---|---|---|
| Main #1 | 146s | Claude C, GPT-Mini A, Gemini B | C | no |
| Main #2 | 101s | Claude C, GPT-Mini A, Gemini C | C | no |
| Control | 117s | all hash, none encrypt | argon2id hashing | no |
| Baseline | 50s | | C | |

| Check | Result |
|---|---|
| First Reading positions | Pass. Three options in run 1, two in run 2. |
| Split section | Partial. Names who disagreed and why, but the split left is narrow: C alone first, or C and B together. |
| Debate effect | Pass, with a caveat. Both weaker members switched to the strongest member's position. GPT-Mini picked A and dropped it in both runs, after a thin critique. |
| Risks | Weak pass. It adds two points the baseline doesn't make: whether the blocking queries are reads or writes, and how fragile the freeze is politically. The baseline is more concrete on fixes. |
| Speaker fairness | Fail. The Speaker was also a member and sided with itself in every split; see #73. |
| Control | Pass. It agreed on the main question. The split it reported is on real side issues: PBKDF2 as a fallback, security questions, argon2 variants. |
| Stability | Pass. Same verdict and the same first steps both times. |
| Verdict vs baseline | Marginal. The same answer in about 3x the wall time. What it adds is the reads-or-writes framing. |

**Verdict:** at this setup the parliament gives the same answer as its strongest
member. The disagreement in First Reading is real, but the debate mostly
converges on the strongest member rather than sharpening the split, and the
Speaker's judgement of the split cannot be trusted while it is a member (#73).

**Bugs found:**
- #72: the synthesis parser strips bold markers from section edges, leaving a
  stray `**` in the verdict.
- #73: on tied tiers the first member is always the Speaker, and it credits
  itself.
- #74: `doctor` and `ask` crash with `UnicodeEncodeError` when output is
  redirected on Windows. `--json` is unaffected.

**Not yet run:** step 5 (TUI) and the Windows-specific checks above.
