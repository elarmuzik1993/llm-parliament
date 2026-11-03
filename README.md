# LLM Parliament

[![PyPI version](https://img.shields.io/pypi/v/llm-parliament.svg)](https://pypi.org/project/llm-parliament/)
[![Python](https://img.shields.io/pypi/pyversions/llm-parliament.svg)](https://pypi.org/project/llm-parliament/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://github.com/elarmuzik1993/llm-parliament/blob/main/LICENSE)
[![CI](https://github.com/elarmuzik1993/llm-parliament/actions/workflows/ci.yml/badge.svg)](https://github.com/elarmuzik1993/llm-parliament/actions/workflows/ci.yml)

**A review panel for solo developers.** When you face a hard-to-undo technical
decision and have no team to argue it with, LLM Parliament puts it to two or
three models, ideally from different labs. They answer on their own, critique each other, and
an outside Speaker writes the verdict: what they agree on, where they still
split, the risks any of them raised, and a recommendation. Your coding agent
can call it mid-task.

## What it does

A debate runs in three phases:

1. **First Reading.** Each member answers the question independently and states its position.
2. **Debate.** Each member reads the others and critiques them. A member may change its mind.
3. **Division.** A Speaker that took no part in the debate writes the verdict:
   Consensus, Split, Risks, Recommendation. It also says whether the members
   still disagree (`contested`) and on what.

From a real decision: how an amp plugin should map digital level to input volts.

```json
"summary": {
  "contested": true,
  "contested_on": "0 dBFS = 1 V peak (Grok) or +12.2 dBu / 4.47 V peak (Gemini)"
}
```

The same verdict caught a wrong number in the question itself: +8 to +12 dBu
is 2.8 to 4.4 V peak, not 2 to 3.5 V.

## Why a solo developer would use it

Each point comes from a real run, logged in
[`docs/live-test-windows.md`](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/live-test-windows.md).

- **It checks your own brief.** In two of three real decisions it corrected the
  question: a wrong voltage range, and a CPU target it judged unrealistic, which
  it turned into a stretch goal.
- **The members check each other.** In one debate a member withdrew three
  claims after critique. In another, members corrected a member's account of
  the Redis licence history.
- **You see the disagreement, not just an answer.** One model gives one
  confident answer. A debate names the split, so you know which questions are
  still open and what would change the choice.
- **It reorders your plan by risk.** On the CPU-budget decision, the panel moved
  the riskiest part to the front, so problems show up early.
- **It lives in your editor.** Through MCP, Claude Code (or Cursor, or Codex)
  can call it when it reaches a decision. Every verdict is saved as a file, so
  you get a decision log for free.
- **Start cheap, escalate when it matters.** `ask` gets one model's second
  opinion and `consult` gets several independent answers. You can save a full
  `debate` for when they disagree.

## When to use it

Use it for hard-to-undo decisions with real trade-offs. A question is worth a
debate when it passes three tests:

1. **It is expensive to reverse.** Once it ships, changing it breaks users,
   data or saved work.
2. **Everything after it depends on it.** An architecture, a data model, a
   performance budget: a wrong call here costs weeks, not a revert.
3. **A quick experiment won't settle it.** If an afternoon's prototype or
   benchmark gives the answer, run that instead.

The three real decisions in the log passed all three:

| Decision | Why it was worth a debate |
|---|---|
| How the plugin maps digital level to input volts | Once released, changing it changes how every saved preset sounds. |
| How to turn the amp circuit into code | Every later stage of the plugin is built on it. |
| The CPU and latency budget | Every later feature has to fit inside it. |

## What to expect

It is a double check, not an oracle. Before you commit to an important
decision, two or three independent models test your reasoning and each
other's. When they agree after trying to pick each other apart, you can
commit with more confidence. When they don't, you know exactly where the
doubt is, before it costs you a rewrite.

What it doesn't do:

- **It won't pick a better option than one good model.** Its value is the
  checking: the caught mistakes, the named split and the gathered risks.
- **It adds nothing on easy or settled questions.** One model is enough there.
- **It needs an even panel.** One strong model with two cheap ones just echoes
  the strong one.
- **Agreement raises confidence; it is not proof.** Models can share a blind spot.

## Quick start

```bash
pipx install "llm-parliament[mcp] @ git+https://github.com/elarmuzik1993/llm-parliament.git"
export OPENROUTER_API_KEY=sk-or-...   # one key for models from several labs
parliament doctor                     # checks the install; the wizard proposes a panel
parliament ask "Should my app store user uploads in Postgres or in object storage?"
```

> **Install from git until 0.3.0.** This README describes `main`. The 0.2.0
> release on PyPI predates OpenRouter, Groq, Mistral and the MCP server, so
> `pipx install llm-parliament` does not have them yet.

No key yet? `parliament ask "..." --mock` runs the whole flow on fake models
for free. Already have Anthropic, OpenAI, Google, Groq or Mistral keys, or a
local Ollama? Those work directly. See the
[usage guide](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/usage.md#providers).

## Use it from your coding agent (MCP)

`parliament mcp` runs your panel as an [MCP](https://modelcontextprotocol.io)
server with three tools, from cheapest to most thorough:

| Tool | What it does | Use it for |
|---|---|---|
| `ask(member, question)` | One model answers, with no debate. Any panel member or the outside Speaker. | A quick second opinion from a different model |
| `consult(question, members?)` | Two or more panel members answer independently and in parallel, each with its stance. Nothing judges whether they agree. | Seeing whether models agree before paying for a debate |
| `debate(question)` | The full three-phase debate and verdict | A consequential decision with real trade-offs |

The models cannot see your files, so the agent has to put the context in the
question. Every answer is saved under `~/.parliament/hansards/`.

The Quick start install includes the server. Then register it with Claude Code:

```bash
claude mcp add --scope user parliament -- parliament mcp
```

Cursor and Codex setup, result fields and timeouts are in the
[usage guide](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/usage.md#coding-agents-mcp-in-detail).

## Cost and time

A debate makes 2n+1 model calls (7 for three members), so it costs about 7×
one call. Measured on OpenRouter:

| Panel | Speaker | Per debate | Time |
|---|---|---|---|
| Grok 4.7, GPT-6.1 Sol Pro, Gemini 4 Argon (November 2026) | Opus 5.5, outside | about $0.40–0.50 | 4.5–7.5 min |
| Sonnet 5.5, GPT-5.6 Sol, Gemini 3.1 Pro (October 2026) | Grok 4.7, outside | about $0.25 | 1.5–3 min |
| Sonnet 4.6, GPT-4o-mini, Gemini 2.5 Flash (October 2026) | a member | under $0.10 | 1.5–3 min |
| Local Ollama models | any | $0 | depends on your hardware |

A single call to one of those models took 20–50 seconds. `ask` is one call.
`consult` is one call per member asked.

## Configure

The first-run wizard writes `~/.parliament/config.yaml` from the keys and local
models it finds. Change the panel in the TUI (`parliament`) or in the file.
Use an outside Speaker, a model not on the panel, so the judge has no position
of its own to defend.

- [Usage guide](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/usage.md): install per OS, providers, CLI and TUI, MCP details
- [Configuration reference](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/configuration.md): every key, default and override
- [Hansard JSON schema](https://github.com/elarmuzik1993/llm-parliament/blob/main/docs/hansard-schema.md): the output of `parliament ask --json`

## Contributing

This is my first public project. Feedback, issues and pull requests are
very welcome. Start with
[CONTRIBUTING.md](https://github.com/elarmuzik1993/llm-parliament/blob/main/CONTRIBUTING.md),
the [good first issues](https://github.com/elarmuzik1993/llm-parliament/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
or the [roadmap](https://github.com/elarmuzik1993/llm-parliament/issues/15).
The test suite runs on mock providers, so you need no API key. Coding agents
should read [AGENTS.md](https://github.com/elarmuzik1993/llm-parliament/blob/main/AGENTS.md)
first.

## Privacy

No telemetry. Your question goes only to the providers you configure. Keys stay
in your OS keyring or `~/.parliament/keys.env`, and saved verdicts stay in
`~/.parliament/hansards/`. All outbound calls are in `src/parliament/providers/`
and `src/parliament/model_catalog.py`. You are responsible for following each
provider's terms of use.

## License

[AGPLv3](https://github.com/elarmuzik1993/llm-parliament/blob/main/LICENSE). See
[CHANGELOG.md](https://github.com/elarmuzik1993/llm-parliament/blob/main/CHANGELOG.md)
for the release history.
