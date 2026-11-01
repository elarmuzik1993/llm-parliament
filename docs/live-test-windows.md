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

## Results: 2026-10-10, judge swap

Does the verdict reflect the debate or the judge? The eight saved debates
above were re-judged, with each transcript held fixed and only the Division
step re-run. Judges:
- Grok 4.7 again, to measure its own variation.
- DeepSeek V4 Pro and Kimi K2.6, two more outside models.
- Claude Sonnet 5.5, the same model as one member. Its input is anonymised as
  usual.

That is 32 calls, costing $0.73. Verdicts are read from each judge's opening
line, by hand where pattern matching failed.

| Run | Members' final positions (Claude, GPT, Gemini) | Live verdict (Grok) | Grok again | DeepSeek | Kimi | Sonnet |
|---|---|---|---|---|---|---|
| 1 | C, B, B | B | B | B | B | B |
| 2 | C, B, B | B | B | B | B | B |
| 3 | C, B, B | B | B | B | B | B |
| 4 | A, A, A | A | A | A | A | A |
| 5 | B, B, B | B | B | B | B | B |
| 6 | C, A, A | A | A | A | A | **C** |
| 7 | A, B, A | B | B | B | A | A |
| 8 | C, B, B | B | B | B | B | **C** |

**The verdict comes from the debate, not from an outside judge.** The three
outside judges agree on 7 of 8 debates. Grok gave the same verdict on every
re-judge. The one split is run 7, the closest debate. There the members ended
2–1 for A, but both of them had made A conditional on evidence nobody had.
Grok and DeepSeek chose B on that ground; Kimi followed the majority. So the
6-to-2 spread across runs in the section above comes from what members argued
in each debate, not from Grok's lean.

**A judge that shares a model with a member sides with it.** In runs 6 and 8
the Sonnet judge chose C. That was the position of the Claude member (also
Sonnet 5.5), and no outside judge chose it. In run 8 it overruled a 2–1
majority, saying "headcount is not evidence". In both runs it agreed with that
member against the outside judges. Anonymising the input did not stop this: a
model recognises its own arguments without names. This is the #73 failure in
a weaker form.

**Consequences:**
- Use an outside Speaker from a vendor not on the panel. The default, a
  member as Speaker, keeps this bias even with anonymised input.
- Done in #79: `parliament ask` warns when `parliament.speaker` uses the same
  model as a member, and when tied members leave the Speaker to be picked by
  order.


## Results: 2026-11-01, self-reported positions

One debate to check #69 (self-reported positions), #87 (panel warnings) and the
family tier rules from #88 against real models. `main` at `1556618`. Members:
`anthropic/claude-opus-5.5`, `openai/gpt-5.1`, `google/gemini-3.1-pro-preview`.
Speaker: `x-ai/grok-4.7`, outside the panel. The question is the memory-safety
rewrite above. The member prompts have changed since those runs (the
`POSITION:` and `CHANGED MIND:` lines), and two members are different models,
so this run cannot be counted with the eight above.

| Wall | First Reading | After Debate | Verdict | Degraded | Cost |
|---|---|---|---|---|---|
| 112s | Claude A, GPT C, Gemini C | Claude A, GPT C, Gemini C → A | A | no | $0.17 |

| Check | Result |
|---|---|
| `POSITION:` line | Pass. All six responses end with it, and it parses into `position.stance`. |
| `CHANGED MIND:` | Pass. All three Debate responses carry it. Gemini said yes, and its stance moved from C to A; the other two said no and kept theirs. |
| Split section | Pass. Names who chose what, each side's strongest argument, and that Gemini switched on the IPC-cost and "second parser" points. This agrees with Gemini's own `CHANGED MIND: yes`. |
| Family tier rules | Pass. All three members resolve to tier 1 `frontier (inferred)`; `unrated_members` is empty. |
| Panel warnings | Not tested. This panel raises none, so `warnings` is `[]` and there was nothing to see on screen. A mixed-tier panel or an insider Speaker is needed for that. |
| Speaker fairness | Pass. The verdict follows the final 2–1 majority, and the Recommendation gives the conditions for switching to C. |

The plan matches the eight runs above: the verdict starts with a first-week
review of where the six past bugs were, and both A and C are gated on it.

**Found:**
- #89: the Hansard records the Speaker only as `speaker_name: "Speaker"`, so the
  file does not say that `x-ai/grok-4.7` judged it. Comparing judges (see the
  judge swap above) needs the model.
- The outside Speaker is from an unrated vendor (xAI), but nothing reports it:
  `unrated_members` and `warnings` cover members only. Noted on #89.

## Results: 2026-11-01, debate against single calls

Same panel and outside Speaker as the run above. Four more debates and 18
single calls, to compare the debate with each model asked alone. Single calls
use the bare question with no system prompt, three tries per model, as in the
contested-questions section. Picks were read by hand from each answer's opening.

**Memory-safety rewrite.** Two more debates: one on the code from #92 (the
`contested` flag), and one through `parliament mcp` from #93.

| Run | Wall | First Reading | After Debate | Verdict | `contested` |
|---|---|---|---|---|---|
| Positions run above | 112s | Claude A, GPT C, Gemini C | Gemini C → A | A | (not yet recorded) |
| #92 | 99s | Claude A, GPT C, Gemini A | no change | A | true: "A versus C" |
| `parliament mcp` | 175s | Claude A, GPT C, Gemini A | no change | A | true: "A versus C" |

| | Claude | GPT | Gemini |
|---|---|---|---|
| Bare question, alone | A, A, A | B, B, B | B, B, B |

The parliament chose A every time, against the B that two of the three models
give alone. That is mostly the wording, not persuasion. Under the First Reading
prompt GPT and Gemini open on C or A, never B, and only one member in three
debates changed its mind. This matches the contested-questions section: on this
question the letter moves with the wording and the panel, and the plan does
not.

**Analytics database.** A new question. The 2026-10-10 screen split the
earlier panel on this topic, but it had no full debate yet.

> We are a 12-person B2B SaaS company on one Postgres database (400 GB, growing 20 GB a month). Customers now want in-app analytics dashboards over the last 2 years of their own event data, with queries answering in under 2 seconds. Two engineers can work on it for one quarter. Choose exactly one: (A) keep Postgres and add partitioning, materialized views and a read replica, (B) add ClickHouse, fed from Postgres by change data capture, (C) use a managed warehouse (BigQuery or Snowflake) with an hourly sync, and cache results in the app. Pick one, justify it, and say what would change your mind.

| | Claude | GPT | Gemini | Verdict | `contested` |
|---|---|---|---|---|---|
| Alone, three tries | B, B, B | B, B, B | A, A, A | | |
| Debate 1 (93s) | B | B | A → B | B | false |
| Debate 2 (103s) | B | B | A → B | B | false |

Gemini switched in both debates, and for a true reason it had missed: native
Postgres materialized views only refresh in full, so option A turns into
hand-built rollups as the data grows. Its peers made that point; it named it in
its reply. The `contested: false` is correct, since all three ended on B.

**Risk coverage.** Eight risks from the first verdict were searched for in the
nine single calls by keyword:
- a stalled replication slot retaining WAL until the primary fills;
- full-refresh materialized views;
- cross-tenant leaks;
- deletes, GDPR and dedup in CDC;
- a week-one benchmark as the kill criterion;
- replica replay conflicts;
- partition count;
- warehouse cold start and per-query cost.

The best single answer covered 6 of them, and Gemini's alone covered 0 to 2.
The two verdicts covered 8 and 6, at about 2,800 characters each against
2,700 to 9,100 for the single answers. The replay-conflict risk was in 1 of 9
single answers, the WAL risk in 2, and partition count in none.

This check favours the verdict: the list comes from the verdict, so the
first verdict covers all eight by construction. Nor was it checked what the
single answers raised that the verdicts dropped. A fair score needs a risk
list fixed beforehand and a blind grader.

| Check | Result |
|---|---|
| Debate effect | Pass on the analytics question: a member corrected a factual error after a peer's critique, twice. Weak on the rewrite: one change in three debates. |
| `contested` flag | Pass. True on the 2–1 rewrite debates and false on the unanimous analytics debates, and `contested_on` names the real choice. |
| Verdict vs baseline | Mixed. On the analytics question, the same decision as the single-call majority, with a fuller risk list and a kill criterion. On the rewrite, a different decision from two of three models, driven by the prompt. |
| Stability | Pass. A in 3 of 3 for the rewrite, B in 2 of 2 for the analytics question. |

**Verdict:** the debate does not give a more correct letter than one model. Its
value here is narrower: it catches a member's factual error, it reports when
strong models still disagree and on what, and it gathers risks that the single
answers each cover only in part. A test on questions with a known right answer,
where one model tends to be wrong, would measure the first of these directly.

**Found:** the installed tool ran from a branch without #91, so these
Hansards have no `speaker_model`.

Cost: the rewrite debates about $0.20 each; the single calls and analytics
debates $1.25 together, more than estimated, mostly the Opus single calls.
