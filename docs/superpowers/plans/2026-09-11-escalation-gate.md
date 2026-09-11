# Escalation Gate — Strategy & Validation Plan

> **Status:** proposal. Nothing here is committed to. Phase 1 is a go/no-go gate on
> everything after it; if it fails, this document should be closed, not revised.

**Goal:** Establish whether inter-model disagreement is a usable signal for *when an
autonomous agent should stop and ask a human* — and if it is, ship that signal as a
callable primitive.

**Thesis in one line:** Every existing agent gate triggers on *what the agent is about
to do*. None trigger on *whether the decision is hard*.

**Spec source:** none yet. This plan precedes a spec deliberately — Phase 1 may end it.

---

## 1. The claim, stated weakly on purpose

The tempting claim is that models "have their own reasoning" and therefore disagree
meaningfully. That is not required and should not be built on.

The claim this plan rests on is weaker and already testable today:

> Different training corpora, RLHF, and architectures produce different inductive
> biases. Those biases **diverge more on genuinely underdetermined questions than on
> settled ones** — because the training distribution contains real human disagreement
> about one and near-consensus about the other.

The models are sampling the shape of human disagreement. That is enough. If stronger
claims about model reasoning turn out to be true later, this design gets better for
free — but it must not *require* them.

**Design rule:** never ship something that depends on a future capability arriving.

---

## 2. Why this is an unoccupied position

Approval gates are not new. Claude Code prompts before running commands, LangGraph has
interrupts, human-in-the-loop approval is a product category. Claiming "nobody does
this" is false and will be corrected in the first five minutes of any conversation.

The precise gap:

| Existing gates | This |
|---|---|
| Trigger on action category (`rm -rf`, file write, migration) | Triggers on epistemic state (is this contested?) |
| A syntax check | A semantic check |
| `DROP TABLE` prompts; "which architecture should we commit to" does not | The second has the larger blast radius |

`degraded=True` (`core/types.py`) is already a proto-escalation signal: it exists
because a verdict built from fewer members than configured is a weaker thing to act on.
This plan generalises that instinct.

---

## 3. The constraint that is actually the product: calibration

Every alerting system dies the same death — it fires too often, humans learn to click
through, and it becomes *worse than nothing* because it launders responsibility.

- A gate that escalates 40% of the time is noise with good typography.
- A gate that fires rarely and is right when it fires is the entire value proposition.

**Calibration is not polish.** It is why Phase 1 exists and why Phase 3 must not ship
before Phase 1 produces a threshold.

---

## Phase 0 — Instrumentation (prerequisite, ~1 week)

Nothing here is a product feature. It exists so every later phase is cheap.

- [ ] **Token + cost per phase.** `Response` carries `duration_ms` and nothing else.
      Add token counts and resolved cost; surface at `archive` level and in `--json`.
      Without cost, none of this becomes a trade-off argument.
- [ ] **Structured positions on `Synthesis`.** `split` is prose today. Add
      `positions: list[Position]` — `(member, stance, changed_mind: bool)`. The Debate
      prompt *already asks* "have they changed your mind on anything?" and the answer
      currently dissolves into text. This is the single highest-value change in the plan:
      every later phase needs disagreement as data, not regex-on-prose.
- [ ] **`--no-debate` flag.** `run_division()` takes a `list[Response]` and does not care
      which phase produced it, so First Reading responses can be passed straight through.
      Enables the Phase 2 ablation.
- [ ] **Batch runner.** questions file → N Hansards → JSON. Pure test harness.

| Path | Change |
|---|---|
| `core/types.py` | `Response.tokens/cost`; new `Position`; `Synthesis.positions`, `Synthesis.contested` |
| `procedures/division.py` | Emit structured positions; parser fallback must still hold |
| `core/parliament.py` | Thread `--no-debate` through `ask()` |
| `providers/*.py` | Return token usage from each provider's response |
| `scripts/` or `evals/` | Batch runner |

---

## Phase 1 — Does the split track contestedness? (GO / NO-GO)

**The only question that matters.** Everything downstream is void if this fails.

Build ~30 questions where the answer's *difficulty* is known in advance:

- **Settled:** "Should we salt password hashes?" · "Should secrets live in the repo?"
  · "Should this endpoint be rate-limited?"
- **Contested:** "Monorepo or polyrepo?" · "REST or gRPC for internal services?"
  · "Should this be a library or a service?"

- [ ] Author and label the set (label before running — no post-hoc rationalising)
- [ ] Run all questions; record positions, split length, cost
- [ ] Build the 2×2: predicted-contested vs actually-split
- [ ] **Pick the escalation threshold from this data**, not from taste

**Kill criteria — write the result down either way:**

> If the system splits on password salting and converges on monorepo-vs-polyrepo, the
> disagreement signal is noise. Close this plan. The finding is still worth publishing —
> it is a negative result nobody in the 141-paper MAD corpus has reported.

**Second eval set, free and sharper:** decisions from this repo's own history where the
outcome is now known. Run it on *"should the default Hansard level be minimal or
verdict?"* and check whether the SPLIT reconstructs the argument that produced the
2026-09-11 flip. Ground truth and reasoning are both already in hand.

---

## Phase 2 — Is the *debate* doing anything? (~1 week)

The honest comparison is not parliament vs. one model. Three arms:

| Arm | Configuration |
|---|---|
| **(a)** | One call to the strongest member |
| **(b)** | Three First Readings, **no debate**, straight to Division |
| **(c)** | Full parliament |

- [ ] Run all three across the Phase 1 set, with cost
- [ ] Report accuracy/agreement **jointly with tokens** — the survey's sharpest gap

If **(b) ≈ (c)**, the debate phase is decoration and a cheaper product is available —
which is a genuinely valuable finding, not a failure. Almost nothing in the MAD
literature isolates this; doing it properly is publishable-adjacent.

---

## Phase 3 — The gate (~1 week, gated on Phase 1)

Minimal surface. One call. Resist every temptation to add more.

```
parliament.deliberate(question, context)
→ { verdict: "escalate",          # proceed | caution | escalate
    contested: true,
    positions: [...],             # who held what, who moved
    cost: {tokens, usd},
    hansard: "hansard://2026-09-11-billing-split" }
```

- [ ] MCP server as a fourth surface beside CLI/TUI/JSON — `render/` already has the
      `DebateRenderer` ABC and `build_renderer()` factory for exactly this
- [ ] Policy layer mapping split-degree → `proceed | caution | escalate`, threshold
      from Phase 1
- [ ] Stable Hansard id/URL so the escalation payload is addressable

**The escalation payload is the decision record.** A human who gets woken does not
receive "the AI is unsure" — they receive one screen: the question, where the models
diverged, each side's strongest form. Decision in seconds, not a re-derivation.

Machines read the fields; people read the prose; **it is the same artifact.** That is
what makes this a product rather than two features.

---

## Phase 4 — Dogfood, then write it up (~1 week)

- [ ] Wire the gate into a real agent loop and use it for a week. One week of use
      teaches more than three months of design.
- [ ] Write up Phase 1 + Phase 2 results and the primitive. **The write-up travels
      further than the repo.**

---

## Compounding layer (later, not now)

Hansards are already persisted to `~/.parliament/hansards/` and **never read back**.
A retrieval path turns the archive into "have we decided something like this before?"
— the long-term-memory gap the MAD survey puts at 2.7% of the field. Deliberately
deferred: it is worthless until Phase 1 says the signal is real.

---

## Explicitly not building

- **LLM-as-judge as a primary metric.** Using a model to score a debate between models
  measures agreement, not quality; the survey flags inter-agent sycophancy directly.
  Secondary signal at most.
- **Unblinded self-rating.** For anything subjective: generate (a) and (c), strip
  identifying formatting, shuffle, rate blind. n=1 blinded beats n=50 unblinded.
- **Chasing MMLU/GSM8K.** That is the domain this tool is *not* in; reproducing known
  benchmark results proves nothing about contested decisions.
- **Majority voting.** It works by deleting the split — the product.
- **More debate rounds, personas, topologies** until Phase 1 lands. Diffusion is the
  failure mode, not failure.

---

## Positioning

Stop selling "multi-agent debate" — crowded, academic, and the 7–15% accuracy figure is
borrowed from ground-truth domains this tool does not operate in.

Sell the gate:

> *Agents ask permission based on what they're about to do.
> None ask based on whether it's a hard call.*

---

## Honest summary of the bet

The engineering is done and it is good: provider abstraction, phase separation, typed
JSON-serializable core, abort-vs-degrade discipline, 460 tests, cross-platform CI. The
expensive part is finished, and it is modular enough to pivot without a rewrite.

What is unproven is one sentence: **that the split correlates with real contestedness.**
If it does, this is a primitive nobody owns. If it does not, the gate is a random number
generator with excellent typography.

Point everything at that one question for a month.
