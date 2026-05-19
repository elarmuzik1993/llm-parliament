# LLM Parliament

[![PyPI version](https://img.shields.io/pypi/v/llm-parliament.svg)](https://pypi.org/project/llm-parliament/)
[![Python](https://img.shields.io/pypi/pyversions/llm-parliament.svg)](https://pypi.org/project/llm-parliament/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

Multi-agent debate for better AI decisions. Research-backed, local-first.

Three AI models debate your question through a parliamentary process:
First Reading, Debate, and Division. The result is a structured verdict with
consensus, split views, risks, and a recommendation.

Built on multi-agent debate, a technique shown to improve AI accuracy by
7-15% in research (Liang et al. 2023, Chen et al. 2023).

See [CHANGELOG.md](CHANGELOG.md) for the release history.

---

> 👋 **This is my GitHub and developer debut!**
> `llm-parliament` is the first project I've shipped publicly. I built it to learn,
> and I'd genuinely love your help making it better.
>
> Feedback, bug reports, feature ideas, code review, and pull requests are **very
> welcome** — no contribution is too small. If something feels confusing, doesn't
> install, breaks on your terminal, or could be more polished, please
> [open an issue](https://github.com/elarmuzik1993/llm-parliament/issues/new) or
> say hi in [Discussions](https://github.com/elarmuzik1993/llm-parliament/discussions).
>
> Stars also help me see what's resonating. Thanks for taking a look. 🙏

---

## Quick Start

```bash
pipx install llm-parliament
parliament doctor
parliament              # opens the TUI
```

The mock parliament runs out of the box with no setup.

## Installation

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
- Keys are stored in `~/.parliament/keys.env` (`%USERPROFILE%\.parliament\keys.env` on Windows) with restricted permissions on Unix.

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

## Configuration

Your personal config lives at `~/.parliament/config.yaml` (or
`%USERPROFILE%\.parliament\config.yaml` on Windows) — outside the repo, so
your settings never end up in git.

On first run, a default mock-only config is copied from the bundled
`config.example.yaml`. The mock config works immediately with no setup so
you can verify the install. Edit it via `parliament members`, the TUI, or
directly in your editor to swap in real models.

The repo only ships `config.example.yaml` (the template). The runtime
`config.yaml` is gitignored.

## Optional: Local Models (Ollama)

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

## Optional: Cloud Models

To use Anthropic, Google, or OpenAI, set the corresponding API key:

```bash
parliament keys set anthropic sk-ant-...
parliament keys set google ...
parliament keys set openai sk-...
```

Then edit `~/.parliament/config.yaml` (or use the TUI) to add cloud
members:

```yaml
parliament:
  members:
    - name: Claude
      provider: anthropic
      model: claude-haiku-4-5-20251001
    - name: Gemini
      provider: google
      model: gemini-2.0-flash-lite
```

Keys are stored in `~/.parliament/keys.env` with `chmod 0600` on Unix.
You can also export `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and
`GOOGLE_API_KEY` directly in your environment if you prefer.

Useful key commands:

```bash
parliament keys list
parliament keys remove openai
```

## Does it cost 3× more?

Yes — Parliament makes more API calls than asking a single model: 3 for First
Reading, 3 for Debate, 1 for Division (7 total). On cloud APIs, that's real money.

**Approximate cost per query:**

| Setup | Cost | When to use |
|-------|------|-------------|
| Single GPT-4o | ~$0.02 | Quick lookups, drafting, anything with an obvious answer |
| Parliament — 3× cheap (Haiku + Flash-Lite + GPT-4o-mini) | ~$0.04–0.06 | Decisions with real trade-offs |
| Parliament — 3× mid-tier (Sonnet + GPT-4o + Flash) | ~$0.15–0.30 | High-stakes architecture or strategy calls |
| Parliament — local Ollama models | ~$0.00 | Any decision, no API cost |

**The right question is whether that cost is worth it for the specific decision.**

Parliament is designed for decisions where being wrong is expensive — architecture
choices, technical trade-offs, strategy calls. Getting those wrong can cost days
or weeks of rework. The token cost of a debate is a rounding error compared to
the cost of a wrong call.

For quick lookups, summaries, or anything with an obvious answer, use a single
model. Parliament is a deliberation tool, not a throughput tool.

**Three reasons the cost argument flips:**

1. **Tier mixing closes the gap.** One strong model for Division + two fast cheap
   models for First Reading and Debate is the default wizard preset — total cost
   is close to a single mid-tier call, with multi-perspective quality.

2. **Local models make it free.** Ollama runs 3B–13B models on commodity hardware
   at no API cost. For anyone who can run two small local models, the "3×" concern
   disappears entirely.

3. **One good answer beats three mediocre ones.** A single-model answer on a hard
   architectural question has blind spots the model doesn't know it has. The debate
   surfaces them. If it prevents one wrong architectural decision, it has paid for
   months of usage.

**Three ways to keep costs low:**

| Approach | Effect |
|----------|--------|
| Mix cheap models for First Reading + Debate, one strong model for Division only | Total cost comparable to a single mid-tier call |
| Run local Ollama models for some or all members | No API cost — just electricity |
| `parliament ask "..." --mock` | Zero cost — useful for exploring the format |

The first-run wizard (`parliament doctor` on a fresh install) automatically
suggests a cost-aware preset based on what keys and local models you have
available. You can also mix cloud and local: e.g. one Anthropic member + two
Ollama members keeps the cloud bill minimal while still getting the debate benefit.

**Rule of thumb:** if the cost of being wrong on this decision exceeds $1, the
debate is worth it.

## CLI Usage

```bash
# Check that the install is healthy
parliament doctor

# Use mock providers for fast local testing
parliament ask "Is this architecture too complex?" --mock

# Show the full transcript before the verdict (post-hoc dump)
parliament ask "Which queue should we use?" --verbose

# Hide the live debate panels and only print the final verdict
parliament ask "Quick check?" --no-show-debate

# Choose the Speaker for the final synthesis
parliament ask "What are the main risks?" --speaker Claude

# Show configured members
parliament members

# Open the full TUI dashboard
parliament

# Open the TUI with mock providers, no Ollama/API keys needed
parliament --mock

# Browse the same dashboard with a specific config
parliament tui --config /path/to/custom-config.yaml
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

By default, both the post-run terminal output and the saved `.md` file
contain the four-part Speaker synthesis (Consensus, Split, Risks,
Recommendation) — no LLM transcripts. Older runs that included the full
debate text by default are now opt-in via `--hansard=full`.

Four levels:

| Level | Includes | Roughly |
|---|---|---|
| `minimal` | Recommendation only | one paragraph — "just tell me what to do" |
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
The level applies to the saved `.md` file **and** the post-run terminal
output. The live in-flight debate view is independent — toggle it
separately with `--show-debate` / `--no-show-debate`.

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

## Development

Clone the repo and create a virtual environment.

Linux / macOS:

```bash
git clone https://github.com/elarmuzik1993/llm-parliament.git
cd llm-parliament

python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[all,dev]"
```

Windows (PowerShell):

```powershell
git clone https://github.com/elarmuzik1993/llm-parliament.git
cd llm-parliament

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[all,dev]"
```

(In `cmd.exe`, use `.venv\Scripts\activate.bat` instead.)

Run the test suite:

```bash
python -m pytest
```

Run Ruff:

```bash
ruff check .
```

Try the CLI without external services:

```bash
parliament ask "What should we test first?" --mock
```

## Project Layout

```text
src/parliament/
  cli.py                  Click CLI (parliament ask / doctor / keys / members / tui / update)
  commands.py             Slash commands (/help, /update, /doctor, /history, /copy, …)
  config.py               YAML config loading, key management, resolve_* precedence helpers
  doctor.py               Health-check logic (Python, curses, terminal, providers, Ollama)
  model_catalog.py        Provider model presets + tier data for pickers
  tui.py                  Curses TUI — all screens, key handling, main loop
  core/                   Parliament orchestrator, dataclasses, ProgressEvent
  procedures/             First Reading, Debate, and Division phases
  providers/              Adapters for Ollama, OpenAI, Anthropic, Google, plus Mock
  render/                 HansardLevel + terminal/markdown renderers + live CLI/TUI views
tests/                    Pytest suite (pytest-asyncio)
scripts/
  diagnose-render.py      Render diagnostic — colors + spinner debugging
config.example.yaml       Default config template (copied to ~/.parliament/config.yaml on first run)
config.cloud.yaml         Cloud-only example (Anthropic + Google + OpenAI)
config.mixed.yaml         Mixed example (Ollama + cloud)
AGENTS.md                 Contributor source-of-truth (architecture, conventions)
CHANGELOG.md              Release history (Keep-a-Changelog)
RELEASING.md              PyPI release procedure
```

## Disclaimer

LLM Parliament is an orchestration framework. It coordinates multiple AI models
to provide structured debate and synthesis. Users are responsible for complying
with the Terms of Service and Usage Policies of their respective LLM providers
(e.g., Ollama, OpenAI, Anthropic, Google). This tool does not bypass safety filters or
usage restrictions of the underlying models.

## License

AGPLv3


 
