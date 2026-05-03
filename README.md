# LLM Parliament

Multi-agent debate for better AI decisions. Research-backed, local-first.

Three AI models debate your question through a parliamentary process:
First Reading, Debate, and Division. The result is a structured verdict with
consensus, split views, risks, and a recommendation.

Built on multi-agent debate, a technique shown to improve AI accuracy by
7-15% in research (Liang et al. 2023, Chen et al. 2023).

## Quick Start

```bash
pipx install llm-parliament    # global install, like `npm i -g`

# Local (free, requires Ollama)
parliament ask "PostgreSQL or MongoDB for analytics?"

# Cloud (requires API keys)
parliament ask "question" --config config.cloud.yaml

# Dev/testing (instant, no setup)
parliament ask "question" --mock
```

## Installation

The recommended way is **pipx** — it installs the tool into an isolated
environment but exposes `parliament` globally on your PATH, so you don't
have to think about virtual environments:

```bash
pipx install llm-parliament
```

Plain `pip` also works:

```bash
pip install llm-parliament
```

For cloud provider SDKs (Anthropic, Google), add the `cloud` extra:

```bash
pipx install "llm-parliament[cloud]"
# or
pip install "llm-parliament[cloud]"
```

On Windows, the install pulls in `windows-curses` automatically so the
TUI works out of the box. The TUI is best run inside Windows Terminal
or PowerShell 7+. Legacy `cmd.exe` works for the basic flow but has
limited cursor and color support. Keys are stored in
`%USERPROFILE%\.parliament\keys.env`; NTFS ACLs default to owner-only
inside the user profile, so file permissions are not set explicitly on
Windows.

The default config uses local Ollama-compatible models and does not need API
keys. Cloud configs require provider SDKs and keys.

## Local Models

The default `config.yaml` uses Ollama through its OpenAI-compatible API at
`http://localhost:11434/v1`.

Install Ollama, start it, and pull the default models:

```bash
ollama pull llama3.1
ollama pull mistral
ollama pull gemma2
```

> **Note for Windows/Slow Hardware:** If local models (like `deepseek-r1`) are slow to respond, you might encounter an `APITimeoutError` in some environments. By default, LLM Parliament uses **no timeout** (`timeout: null`). You can explicitly set a timeout in your `config.yaml` if desired:
> ```yaml
> providers:
>   ollama:
>     base_url: http://localhost:11434/v1
>     timeout: 600.0  # Optional: set a 10-minute limit
> ```

Then ask a question:

```bash
parliament ask "Should we use PostgreSQL or MongoDB for analytics?"
```

## Cloud Models

Use `config.cloud.yaml` for Anthropic, OpenAI, and Google providers:

```bash
parliament keys set anthropic sk-ant-...
parliament keys set openai sk-...
parliament keys set google ...

parliament ask "How should we design our cache invalidation strategy?" \
  --config config.cloud.yaml
```

Keys are stored in `~/.parliament/keys.env` with restricted file permissions on
Unix. You can also set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and
`GOOGLE_API_KEY` directly in your environment.

Useful key commands:

```bash
parliament keys list
parliament keys remove openai
```

## CLI Usage

```bash
# Use mock providers for fast local testing
parliament ask "Is this architecture too complex?" --mock

# Show the full transcript before the verdict
parliament ask "Which queue should we use?" --verbose

# Choose the Speaker for the final synthesis
parliament ask "What are the main risks?" --speaker Claude

# Show configured members
parliament members --config config.cloud.yaml

# Open the full TUI dashboard
parliament

# Open the TUI with mock providers, no Ollama/API keys needed
parliament --mock

# Browse the same dashboard with a specific config
parliament tui --config config.cloud.yaml
```

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
  cli.py                  Click CLI and Rich output
  config.py               YAML config loading and key management
  core/                   Public orchestration and domain types
  procedures/             First Reading, Debate, and Division phases
  providers/              Provider adapters for Ollama, OpenAI, Anthropic, Google
tests/                    Unit tests
config.yaml               Local Ollama config
config.cloud.yaml         Cloud provider config
config.mixed.yaml         Mixed local/cloud config
```

## Disclaimer

LLM Parliament is an orchestration framework. It coordinates multiple AI models
to provide structured debate and synthesis. Users are responsible for complying
with the Terms of Service and Usage Policies of their respective LLM providers
(e.g., Ollama, OpenAI, Anthropic, Google). This tool does not bypass safety filters or
usage restrictions of the underlying models.

## License

AGPLv3


