# Using LLM Parliament

The [README](../README.md) is the short version. This page has the details: installing on each
platform, the first-run wizard, every provider, the CLI and TUI, and the MCP server.
[`configuration.md`](configuration.md) is the key-by-key reference.

- [Installation](#installation)
- [First run and configuration](#first-run-and-configuration)
- [Providers](#providers)
- [CLI usage](#cli-usage)
- [Coding agents (MCP) in detail](#coding-agents-mcp-in-detail)

## Installation

> **Until 0.3.0, install from git.** The 0.2.0 release on PyPI predates
> OpenRouter, Groq, Mistral and the MCP server. In the commands below, replace
> `pipx install llm-parliament` with
> `pipx install "llm-parliament[mcp] @ git+https://github.com/elarmuzik1993/llm-parliament.git"`.

The recommended way is **pipx** — it installs the tool into an isolated
environment but exposes `parliament` globally on your PATH, so you don't
have to think about virtual environments.

### Linux

```bash
# Prereqs (one-time)
sudo apt install pipx          # Debian/Ubuntu — or `pacman -S python-pipx`, `dnf install pipx`
pipx ensurepath                # adds ~/.local/bin to PATH
# Restart your shell.

# Install
pipx install llm-parliament

# Verify
parliament doctor
```

### macOS

```bash
# Prereqs (one-time)
brew install pipx
pipx ensurepath
# Restart your shell.

# Install
pipx install llm-parliament

# Verify
parliament doctor
```

### Windows

```powershell
# Prereqs (one-time)
# 1. Install Python 3.11+ from python.org — check "Add Python to PATH" during install.
# 2. Install pipx:
python -m pip install --user pipx
python -m pipx ensurepath
# 3. Close and reopen Windows Terminal (recommended) or PowerShell.

# Install
pipx install llm-parliament

# Verify
parliament doctor
```

**Notes:**

- All cloud provider SDKs (Anthropic, Google, OpenAI) are bundled. No extras needed.
- Ollama (for local models) is a separate native daemon — install from <https://ollama.com> if you want local models. The `parliament doctor` command tells you what's detected.
- On Windows, the install pulls in `windows-curses` automatically so the TUI works out of the box. Windows Terminal is recommended over `cmd.exe` (better VT/UTF-8 support); legacy `cmd.exe` is supported.
- Keys are stored in the OS native credential store (Windows Credential Manager, macOS Keychain, GNOME Keyring) via `parliament keys set`. Falls back to `~/.parliament/keys.env` if no keyring is available.

## Verify your install

After install, run:

```bash
parliament doctor
```

You'll see something like:

```text
Environment
  ✓ Python 3.12.5 (>=3.11 required)
  ✓ Curses available
  ✓ Terminal: 142x38
  ✓ Config: ~/.parliament/config.yaml (initialized)

Providers
  ✓ Anthropic SDK         ℹ ANTHROPIC_API_KEY not set
  ✓ Google SDK            ℹ GOOGLE_API_KEY not set
  ✓ OpenAI SDK            ℹ OPENAI_API_KEY not set
  ℹ Ollama: not reachable at http://localhost:11434

Next steps
  - Add cloud keys:   parliament keys set <provider> <key>
  - Local models?     Install Ollama from https://ollama.com, then `ollama pull llama3.1`
  - Run the TUI:      parliament
```

Exit code is `0` if the install is functional (regardless of whether you
have keys/Ollama configured), or `1` if something is broken (e.g. Python
too old).

## First run and configuration

Your personal config lives at `~/.parliament/config.yaml` (or
`%USERPROFILE%\.parliament\config.yaml` on Windows) — outside the repo, so
your settings never end up in git.

On first run (triggered by `parliament doctor`, `parliament ask`, or launching
the TUI), a setup wizard runs automatically. It detects your API keys, local
Ollama models, and available RAM, then proposes a matching preset:

```text
Welcome to Parliament. No config found - let's set one up.

Detected:
  ✓ ANTHROPIC_API_KEY (configured)
  ℹ OPENAI_API_KEY (not set)
  ✓ GOOGLE_API_KEY (configured)
  ℹ OPENROUTER_API_KEY (not set)
  ℹ Ollama: not reachable
  System RAM: 16 GB

Proposed preset: cloud-anthropic-google (Anthropic + Google)
  - Claude (anthropic / claude-sonnet-4-6)
  - Claude-Haiku (anthropic / claude-haiku-4-5-20251001)
  - Gemini (google / gemini-2.5-flash)

Use these defaults? [Y/n]:
```

Confirm with `Y` and the config is written. If no keys or Ollama are detected,
you get a working mock preset — no setup needed to verify the install. Edit
members later via the TUI (`parliament`) or directly in the file.

With `OPENROUTER_API_KEY`, the wizard can propose three labs through one
account. Two or three direct provider keys keep their existing presets, and
three reachable local models that fit RAM take priority over OpenRouter.
Otherwise OpenRouter wins over mixed, single-provider and mock presets.
Its proposal warns that API usage may incur charges. Declining any proposal
writes a mock preset, not the next available cloud or local preset.

**[`configuration.md`](configuration.md)** is the complete reference:
every key, its type, its real default, and the environment variable or CLI flag
that overrides it — plus `settings.json`, which the TUI writes and this file
does not cover.

### Choosing the Speaker

The Speaker writes the final verdict. By default it is one of the members: the
strongest by tier, or the first listed when they tie. A model the tool cannot
rate is picked only when no member is rated. In our tests a member
Speaker tended to side with its own position, even with member names hidden
from it. A Speaker that did not debate has no position to defend:

```yaml
parliament:
  members:
    - {name: Claude, provider: openrouter, model: anthropic/claude-sonnet-5.5}
    - {name: GPT,    provider: openrouter, model: openai/gpt-5.6-sol}
    - {name: Gemini, provider: openrouter, model: google/gemini-3.1-pro-preview}
  speaker:
    name: Grok
    provider: openrouter
    model: x-ai/grok-4.7
```

Pick a model that is not on the panel. `parliament ask` warns when the Speaker
shares a member's model, and when tied members leave the choice to list order.
If the outside Speaker fails, a member takes over, and `--speaker <member>`
still overrides it.

## Providers

### Cloud models

**Easiest path: one OpenRouter key.** One signup and one key reach models from
several labs, so you do not need a separate account for each. Export the key
in your shell profile before the first run and the wizard picks it up:

```bash
export OPENROUTER_API_KEY=sk-or-...
parliament doctor   # wizard fires, detects the key, proposes a three-lab preset
```

Usage is billed by OpenRouter. It also lists some free models; check its
[model list](https://openrouter.ai/models) for what is free today, since that
changes. See [OpenRouter](#openrouter) below for the config and key commands.

**Direct provider keys** — if you already have them, export them instead; the
wizard picks those up the same way:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
parliament doctor   # wizard fires, detects keys, writes a cloud preset
```

**After first run** — add or change keys at any time:

```bash
parliament keys set anthropic sk-ant-...
parliament keys set google ...
parliament keys set openai sk-...
```

Keys are saved to the OS native credential store. Then edit members via the
TUI (`parliament`) or directly in `~/.parliament/config.yaml`:

```yaml
parliament:
  members:
    - name: Claude
      provider: anthropic
      model: claude-sonnet-4-6
    - name: Gemini
      provider: google
      model: gemini-2.5-flash
```

You can also export `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and
`GOOGLE_API_KEY` directly in your environment instead of using the keyring.

Useful key commands:

```bash
parliament keys list
parliament keys migrate   # move existing keys.env entries to the OS keyring
parliament keys remove openai
```

### OpenAI-compatible providers (Groq, Mistral, OpenRouter)

Groq and Mistral speak the OpenAI API and are available directly as `groq`
and `mistral` providers. Store each key separately:

```bash
parliament keys set groq gsk_...
parliament keys set mistral your-mistral-key
```

Both providers can coexist with OpenAI and OpenRouter in the same parliament:

```yaml
parliament:
  members:
    - name: Groq
      provider: groq
      model: llama-3.3-70b-versatile
    - name: Mistral
      provider: mistral
      model: mistral-large-latest
```

They appear in the TUI provider picker and `/key`. `parliament doctor` checks
the required keys for configured Groq and Mistral members; they do not have
separate rows in its Providers section.
Groq reads `GROQ_API_KEY`; Mistral reads `MISTRAL_API_KEY`. A missing vendor
key never falls back to `OPENAI_API_KEY`, including during model discovery.
Optional `providers.groq` and `providers.mistral` entries can override the
`base_url` or supply an explicit `api_key`.

Existing `provider: openai` configurations with a custom `base_url` still
work, using `providers.openai.api_key` or `OPENAI_API_KEY` as before. Move to
the named providers to keep vendor credentials and endpoints separate.

Their models retain their tier labels and the usual tier-gap warnings.

#### OpenRouter

OpenRouter is also OpenAI-compatible, but it is common enough to deserve its
own line in `parliament keys`, its own button in the TUI provider picker, and
its own row in `parliament doctor`. Name it directly:

```bash
parliament keys set openrouter sk-or-...
```

```yaml
parliament:
  members:
    - name: Claude
      provider: openrouter
      model: anthropic/claude-sonnet-4.6
```

The address (`https://openrouter.ai/api/v1`) and the key variable
(`OPENROUTER_API_KEY`) come from `model_catalog.OPENAI_COMPATIBLE`; you do not
set a `base_url`. The TUI's model picker fetches OpenRouter's live catalogue
the same way it does for Anthropic, OpenAI, and Google.

### Other OpenAI-compatible endpoints

Any service speaking the OpenAI API that is not its own first-class provider
can use `provider: openai`: point `providers.openai` at its
`base_url` and give it a key. Aggregators such as one-api, self-hosted
gateways, and small vendors that ship only an OpenAI-shaped endpoint all fall
into this category.

### Local models (Ollama)

Ollama runs LLMs locally — free, private, no API keys. Install it
separately, then point a parliament member at it.

1. Install Ollama from <https://ollama.com> and start the daemon.
2. Pull a model:
   ```bash
   ollama pull llama3.1
   ```
3. Edit `~/.parliament/config.yaml` (or use the TUI) to add an Ollama
   member:
   ```yaml
   parliament:
     members:
       - name: Llama
         provider: ollama
         model: llama3.1
   providers:
     ollama:
       base_url: http://localhost:11434/v1
   ```
4. Run `parliament` to start a debate.

> **Note:** All providers default to no timeout (`timeout: null`), so a
> slow local model on modest hardware won't be cut off. If you want a
> hard limit, set `timeout: 600.0` on the relevant `providers.<name>`
> block.

## CLI usage

```bash
# Check that the install is healthy
parliament doctor

# Use mock providers for fast local testing
parliament ask "Is this architecture too complex?" --mock

# Show the full transcript before the verdict (post-hoc dump)
parliament ask "Which queue should we use?" --verbose

# Print the full Hansard as JSON for scripts and jq pipelines
parliament ask "Which queue should we use?" --json

# Hide the live debate panels and only print the final verdict
parliament ask "Quick check?" --no-show-debate

# Make a member the Speaker (overrides parliament.speaker; see "Choosing the Speaker")
parliament ask "What are the main risks?" --speaker Claude

# Show configured members
parliament members

# Open the full TUI dashboard
parliament

# Open the TUI with mock providers, no Ollama/API keys needed
parliament --mock

# Browse the same dashboard with a specific config
parliament tui --config /path/to/custom-config.yaml

# Serve the parliament to coding agents (see "Coding agents (MCP) in detail")
parliament mcp
```

### Live debate view

By default, `parliament ask` and the curses TUI render the debate live: a
panel pops in for each member as their analysis lands, and stage headers mark
the transitions through First Reading → Debate → Division. This makes it
obvious *which* model is currently working and *what* they said.

The view is toggleable via three precedence-ordered sources:

| Precedence | Source | Example |
| --- | --- | --- |
| 1 (highest) | CLI flag | `parliament ask "..." --no-show-debate` |
| 2 | Environment variable | `PARLIAMENT_SHOW_DEBATE=0 parliament ask "..."` |
| 3 | YAML config | `display:\n  show_debate: false` |
| 4 (default) | Built-in | live view is **on** |

`--show-debate` controls whether the live panels appear during the run.

### Hansard detail levels

By default the post-run terminal output is `verdict` — the full four-part
synthesis: what the members agreed on, where they split, the risks any of them
flagged, and the Speaker's recommendation. The split is the part a single model
cannot give you, so it ships without anyone having to ask for it. Prefer the
recommendation alone? `--hansard=minimal`. Saved `.md` files are always written
at `archive` level regardless of the display level, so nothing is lost from the
record either way. Older runs that printed the full debate text are opt-in via
`--hansard=full`.

Four levels:

| Level | Includes | Roughly |
|---|---|---|
| `minimal` | Recommendation only | one paragraph, "just tell me what to do" |
| `verdict` | Full four-part synthesis | **default** — concise but complete |
| `archive` | + YAML frontmatter + session footer | searchable in Obsidian, no walls of text |
| `full` | + First Reading + Debate transcripts | today's full record (≈ what `--verbose` used to print) |

Set the level via three precedence-ordered sources:

| Precedence | Source | Example |
| --- | --- | --- |
| 1 (highest) | CLI flag | `parliament ask "..." --hansard archive` |
| 2 | Environment variable | `PARLIAMENT_HANSARD_LEVEL=full parliament ask "..."` |
| 3 | YAML config | `hansard:\n  level: archive` |
| 4 (default) | Built-in | `verdict` |

`--verbose` continues to work; it's an alias for `--hansard=full`.
The level applies to the post-run terminal output only — saved `.md` files are
always written at `archive`, and `--json` is never gated by level. The live
in-flight debate view is independent — toggle it separately with
`--show-debate` / `--no-show-debate`.

For machine-readable output, `parliament ask --json` prints the complete
Hansard object. See [hansard-schema.md](hansard-schema.md) for the
JSON fields and practical `jq` examples.

TUI controls:

```text
Type                Edit the question field
Enter               Run debate when question is focused
Tab                 Switch between question and members
Up/down or j/k      Move through models
Enter               Open selected member settings when members are focused
s                   Open settings when members are focused; save result from verdict screen
e                   Edit the selected member from the detail view
Left/backspace/Esc  Return from settings to dashboard
Ctrl+U              Clear the question field
Ctrl+S              Save member edits
q                   Quit when focused on members/settings
Ctrl+Q              Quit from anywhere
```

The TUI settings screen lets you set the local directory used for saved
Hansard Markdown responses. By default, saved responses go to
`~/.parliament/hansards`.

Member editing stays inside the TUI. The editor lets you change `Name`,
`Provider`, `Model`, and `Base URL`, while `Tier`, `Role`, and API key status
remain derived and read-only. Model pickers include supported presets plus a
`Custom model` escape hatch.

Inside the member editor, `Enter` opens provider/model pickers when those
fields are focused and saves the edit when the base URL field is focused.

## Coding agents (MCP) in detail

The README covers what the three tools are for and how to install the server. This section has the result fields, client setup, timeouts and the mock panel.

The `debate` result:

- `summary.contested`: whether the members still recommend different courses
  of action after the debate (`null` if the Speaker didn't say), and
  `summary.contested_on`: what they disagree on.
- `summary.positions`, `summary.warnings` and `summary.degraded`.
- `verdict`: the Speaker's consensus, split, risks and recommendation.
- `hansard_path`: the full record, saved under `~/.parliament/hansards/` as
  the same JSON `parliament ask --json` prints
  ([schema](hansard-schema.md)). The members' answers stay in that file:
  together they are larger than agents accept from one tool call.

The `ask` result: `member`, `provider`, `model`, `answer`, `duration_ms` and
`record_path` (a JSON record under `~/.parliament/hansards/asks/`).

The `consult` result: `positions` (each member's self-reported stance),
`answers` (each cut to 8,000 characters, with a `truncated` flag), `degraded`,
`warnings` and `record_path` (the full answers, under
`~/.parliament/hansards/consults/`). It has no `contested` flag: nothing
judges whether the members agree, so the agent compares the stances.

Every result carries a `schema` number that changes when its shape does.

Store keys with `parliament keys set` rather than in your shell profile: an
editor started from a desktop icon does not see variables your shell exports.

**Connect your agent.**

Claude Code:

```bash
claude mcp add --scope user parliament -- parliament mcp
```

Cursor, in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "parliament": { "command": "parliament", "args": ["mcp"] }
  }
}
```

Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.parliament]
command = "parliament"
args = ["mcp"]
tool_timeout_sec = 600
```

If the agent reports that `parliament` is not found, use the full path that
`which parliament` (`where parliament` on Windows) prints. `--config PATH` and
`--speaker NAME` work as they do for `parliament ask`; add them after `mcp`.

**Timeouts.** A debate took three to seven and a half minutes in real use
(2026-11-01 and 11-02), which is longer than some agents wait for a tool. The server reports progress after each member's answer.

| Agent | Works? |
|-------|--------|
| Claude Code | Yes. A call that runs past two minutes moves to the background and finishes there. |
| Cursor (editor) | Yes. It waits up to an hour while progress keeps arriving. |
| Codex | Only with `tool_timeout_sec` raised, as above. The default is 60 seconds. |
| Cursor CLI | No. It stops every tool call after 60 seconds, and the limit can't be changed. |

**Cost.** Each `debate` call makes 2n+1 model calls (7 for three members) at your
panel's prices; see [Cost and time](../README.md#cost-and-time). The tool's
description tells the agent this, and to save it for consequential choices,
not facts or small edits. An `ask` is one model call; a `consult` is n, one per
member asked. A live run on 2026-11-01 (Opus 5.5, GPT-5.1 and
Gemini 3.1 Pro, with Grok 4.7 as outside Speaker) took three minutes and cost
about $0.20. Debates and consults run one at a time: a second call waits for the first.

**Try it free.** `parliament mcp --mock` serves a mock panel, to check the
connection; its verdicts are fake. Without `--mock` the server refuses to start
on a panel made only of mock members, so an agent never acts on a fake verdict.
