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

## Results: 2026-10-10, flagships with an outside Speaker

A rerun to separate the idea from the setup. The first run had an uneven panel
and a Speaker who was also a member. This one runs the code from #78:
anonymous Division input and an outside Speaker. Members:
`anthropic/claude-sonnet-5.5`, `openai/gpt-5.6-sol`,
`google/gemini-3.1-pro-preview`. Speaker: `x-ai/grok-4.7`, which is from a
fourth vendor and did not debate. All three members are unrated. The baseline
is a single call to Sonnet 5.5. Total cost: about $0.44.

| Run | Wall | First Reading picks | Verdict | Degraded |
|---|---|---|---|---|
| Main #1 | 103s | Claude C, GPT C, Gemini C | C | no |
| Main #2 | 88s | Claude C, GPT C, Gemini C | C | no |
| Control | 85s | all hash, none encrypt | argon2id hashing | no |
| Baseline | 21s | | C | |

| Check | Result |
|---|---|
| First Reading positions | Partial. Same option, for overlapping reasons. The main question no longer divides frontier models. |
| Split section | Pass. Names who disagreed and why, on execution: how wide the freeze is, whether parts of B can be added, how confident to be. |
| Debate effect | Pass. Members corrected each other's facts, and Gemini revised its timeline and its view of B. Nobody gave in to the strongest member. |
| Risks | Pass. It adds points the baseline misses. Ordinary Postgres reads don't block writes, so the premise needs diagnosing. PgBouncer transaction pooling breaks ORM session state. A background job that reruns the same query doesn't reduce load. A blanket checkout timeout can leave transactions open. |
| Speaker fairness | Pass. The Speaker sided with GPT on freeze scope, and with Claude and GPT against Gemini's overconfidence. It credited no member with points the member didn't make. |
| Control | Pass. It agreed on the main question. The split it reported is on real details: cost parameters, pre-hashing for bcrypt, migrating legacy hashes. |
| Stability | Pass. Same verdict and the same shape of plan both times. |
| Verdict vs baseline | Pass on depth, not on decision. Same choice, but the debate corrected the premise and the plan in ways the single call did not. |

**Verdict:** with an even panel and a neutral Speaker, the debate does real
work. Members check each other's facts, and the Split can be trusted. But this
question has stopped testing disagreement: frontier models all choose C. The
next run needs a question that frontier models genuinely split on.

**Found:** the two runs here used the code from before the plural fix, so the
Speaker's "Members 1 and 2" stayed unresolved. #78 now restores plural labels.
With an outside Speaker configured, the unrated-members warning still says
"Speaker selection assumes tier 3".

## Results: 2026-10-10, contested questions

Same panel and outside Speaker as above, on the code from #78.

**Screening.** Five candidate questions were each put once to each member on
its own ($0.29). Three of them split the panel 2–1: open-source licensing,
analytics database, and memory-safety rewrite. Claude was the odd one out
every time. Shipping with a known bug and forced two-factor got the same
answer from all three; they would make realistic controls.

**Licensing** (BSL, AGPL, or stay Apache; 2 debates). All three picked BSL in
First Reading both times, so the screen's split did not reproduce. The debate
still corrected facts. Members caught one member's wrong account of the Redis
licence history, and timelines it stated without support, and the verdict
drops them. This is a check on fact-correction, not on disagreement.

**Memory-safety rewrite** (Rust, harden C++, or sandbox the parser):

> A 150k-line C++ network daemon, exposed to the internet, has had 2 memory-safety vulnerabilities a year for 3 years. There are 5 engineers, 2 of whom know Rust. Choose exactly one: (A) rewrite incrementally in Rust, starting with the parser, (B) keep C++ and invest in fuzzing, sanitizers and hardening, (C) put the parser in a sandboxed separate process and leave the rest alone. Pick one, justify it, and say what would change your mind.

**Single calls.** Each model on its own, three tries per wording:

| | Claude | GPT | Gemini |
|---|---|---|---|
| Bare question | A, B, A | B, B, B | B, B, B |
| First Reading wording | A, A, A | B, A, A | C, B, A |

**Eight full debates.** Each cell is First Reading → position after the
Debate; an arrow marks a member who changed its mind.

| Run | Claude | GPT | Gemini | Verdict |
|---|---|---|---|---|
| 1 | C | B | B | B |
| 2 | C | B | A → B | B |
| 3 | C | B | A → B | B |
| 4 | A | A | B → A | A |
| 5 | B | B | B | B |
| 6 | C | A | A | A |
| 7 | A | A → B | C → A | B |
| 8 | C | B | A → B | B |

All eight are valid, and none degraded. Picks were read by hand from each
member's stated choice. Pattern matching misread several of them.

| Check | Result |
|---|---|
| First Reading positions | Pass. At least two options in 7 of 8 runs. |
| Split section | Pass. Names each side, its strongest argument and its rebuttals. |
| Debate effect | Pass. A member changed its mind in 5 of 8 runs, each time citing a peer's argument. Gemini moved most. |
| Speaker fairness | Mostly pass. Seven verdicts follow the members' final majority. In run 7 the Speaker chose B against two members on A, reasoning that the condition both had set for A (bugs concentrated in the parser) was not established. That is defensible, but it shows the outside Speaker also brings a view of its own. |
| Stability | Partial. B in 6 of 8, A in 2 of 8. The first step is the same in all 8: review where the six past bugs were, then commit. |
| Verdict vs baseline | Mixed. See below. |

**What eight runs show:**
- **The verdict is steadier than a single call under the same wording, but not
  steadier than every model.** Under the First Reading wording, single calls
  gave A 6 times, B twice and C once. The parliament gave B 6 times and A twice.
  But GPT and Gemini, asked the bare question, gave B every time, which is
  steadier than the parliament.
- **The verdict letter moves, the plan does not.** Every verdict, A or B,
  starts by reviewing the six bugs, and names the result that would switch it.
  The A verdicts are explicitly gated on that review. The real output is the
  same: "find where the bugs were, then commit". The letter depends on which
  side of that gate the run leans.
- **The Debate does persuade.** In 5 of 8 runs a member moved to a peer's
  position, so the final majority is not just the First Reading count.

**Verdict:** on a genuinely contested question, the parliament does not give
one fixed answer. It gives a consistent decision procedure: the first step, the
evidence that decides, and the conditions for each option. Single calls give a
confident letter that changes with the wording. That is a weaker claim than "a
stable verdict", but it holds across all eight runs, and it is the claim this
evidence supports. The earlier version of this section claimed a stable
verdict after three runs. Five more runs did not bear that out.

**A batch stopped by credit.** An earlier attempt started six debates in
parallel. The account had $5 of credit, and OpenRouter reserves credit for
every request in flight, so most requests were refused with HTTP 402. Five
of those six produced no usable result:
- One lost Claude at First Reading. It finished on two members and was
  correctly marked `degraded`.
- Four stopped with "Not enough members responded" and gave no verdict.

The abort-or-degrade rule held against a real provider failure. The one
clean run from that batch is run 3 above. Check the account balance first
(the key's spending limit is not the balance), and run debates one at a time.

Cost: the screen $0.29, the first four debates $0.91, the repeat test $0.46,
the credit-limited batch about $0.65, the last five debates $1.25.
