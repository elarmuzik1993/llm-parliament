# Install Routine — Design Spec

**Date:** 2026-05-04
**Status:** approved (brainstorming complete, awaiting implementation plan)
**Owner:** Boris

## Problem

Install instructions for `llm-parliament` are inconsistent across machines:

- The README claims `pipx install llm-parliament`, but the package isn't on PyPI — that command fails.
- Editable installs without virtualenvs ("just `pip install -e .` and run `parliament`") have proven fragile across Windows machines (PATH problems, multi-Python conflicts, cmd.exe encoding).
- Cloud provider deps live behind a `[cloud]` extra, so the install command varies based on intent — fragmenting the onboarding path.
- New users hit the same install gotchas every time (Python version, pipx not found, terminal choice on Windows). Each gotcha costs minutes and produces no diagnostic output to share.
- There's no first-run health check — users discover problems when the TUI fails, then have to interpret a Python traceback.

**Goal:** make `parliament` installable in three commands or fewer on any supported OS, runnable immediately after install, and self-diagnosing when something goes wrong.

## Decisions (locked during brainstorming, 2026-05-04)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Distribute via PyPI | **Yes** | Single canonical install command (`pipx install llm-parliament`) on every OS. ~15 min one-time setup pays back on every new install. |
| 2 | Add `parliament doctor` subcommand | **Yes, this release** | Catches Windows install gotchas in one breath; provides a low-stakes verification step right after install. |
| 3 | Prereq detail in README | **Per-OS one-liners** (3 blocks) | Balances "as simple as possible" with "for new users." Each block ≤5 lines. |
| 4 | Cloud SDKs (`anthropic`, `google-genai`) | **Bundled by default** | Single install command for everyone. SDKs are import-on-demand, so zero runtime cost for local-only users. |
| 5 | One-line installer script (`curl \| bash`, `.ps1`) | **No** | Adds CI/maintenance burden, security stigma, opaque to users. Per-OS prereq blocks are short enough. |
| 6 | README structure | **Single doc, 12 sections** (Quick Start + Installation kept separate) | Standard pattern (`httpx`, `rich`, `typer` follow it). New users use Installation; experienced users skim Quick Start. |
| 7 | Doctor symbol set | **`✓ ✗ ℹ`** (UTF-8) | Rich + our UTF-8 reconfig handle these reliably. ASCII fallback unnecessary. |
| 8 | Doctor cloud-key check scope | **SDK importable + key configured only** — no network probe | Network probes are slow, can fail transiently, don't validate keys per-model. |
| 9 | TUI auto-doctor on launch | **No** | Adds startup latency for every run; TUI failure modes are clear enough. |
| 10 | Explicit `httpx` dep in `pyproject.toml` | **Yes** | Doctor's Ollama probe needs it; explicit decouples us from `openai`'s transitive pinning. |
| 11 | Version on first PyPI publish | **0.1.0** (no bump) | First PyPI publish of an existing in-tree version. Semver doesn't require a bump just for publishing location. |
| 12 | Release workflow | **Manual local** (`python -m build && twine upload`); TestPyPI for v0.1.0 only | Solo developer; manual is sufficient. CI automation is a future-when-painful upgrade. |
| 13 | `RELEASING.md` | **Yes, new file** | Release process is contributor knowledge, doesn't belong in user-facing README. |
| 14 | GitHub Actions for PyPI publish | **No, defer** | YAGNI; can add later when manual feels painful. |

## User-facing install commands

The README "Installation" section will contain exactly three OS blocks. Visual symmetry across blocks is intentional — last two lines are identical.

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

**Notes that accompany the blocks:**
- All cloud provider SDKs are bundled — no `[cloud]` extra needed.
- Ollama (for local models) is a separate native daemon; install from <https://ollama.com> if you want local models. The `parliament doctor` command tells you what's detected.
- Windows Terminal is recommended over `cmd.exe` (better VT/UTF-8 support); legacy `cmd.exe` is supported.

## README structure

```
1.  Header & pitch                       (unchanged)
2.  Quick Start                          (trimmed; remove config.cloud.yaml refs)
3.  Installation                         (rewritten — 3 OS blocks above)
4.  Verify your install                  (NEW — explains parliament doctor)
5.  First run / Configuration            (kept from PR #2)
6.  Optional: Local Models (Ollama)      (rewritten with "optional" framing)
7.  Optional: Cloud Models               (kept; drop config.cloud.yaml refs)
8.  CLI Usage                            (kept; add `parliament doctor` to examples)
9.  TUI Controls                         (kept)
10. Development                          (kept)
11. Project structure                    (already trimmed in PR #2)
12. Disclaimer / License                 (unchanged)
```

**Key structural choices:**

- Quick Start and Installation are both kept. Quick Start is a 3-line block for users who already have pipx; Installation is the full per-OS prereq guide for newcomers. This duplication is standard and serves two audiences.
- Ollama is framed as **optional**, not as the default. The default config (PR #2) is mock-only, so the out-of-the-box experience requires no Ollama install.
- "Optional: Local Models" and "Optional: Cloud Models" are parallel sections following the same pattern: *what you need → install/configure → edit config example.*
- The existing "Note for Windows/Slow Hardware" timeout block becomes a small side note, since timeouts now default to `None` across all providers.

## `parliament doctor` command

A single subcommand on the existing `parliament` CLI group. Runs a fixed checklist, prints rich-colored bullets, exits 0 (functional install) or 1 (broken install).

### Checks

| # | Check | Pass | Warn / Info | Fail (exit 1) |
|---|---|---|---|---|
| 1 | Python version | `≥3.11` | — | `<3.11` |
| 2 | Curses can `initscr()` | yes | — | no (Windows only) |
| 3 | Terminal size | `≥80×24` | smaller (warn) | — |
| 4 | Config initialized | `~/.parliament/config.yaml` exists or auto-created | — | — |
| 5 | Per cloud provider (anthropic, google, openai): SDK importable + key set | both | SDK ok, key missing | SDK can't import |
| 6 | Ollama daemon at `localhost:11434/api/tags` (2s timeout) | reachable + count of models | not reachable | — |

### Sample output (functional install, no extras)

```
Environment
  ✓ Python 3.12.5 (≥3.11 required)
  ✓ Curses available
  ✓ Terminal: 142×38
  ✓ Config: /home/boris/.parliament/config.yaml (initialized)

Providers
  ✓ Anthropic SDK         ✓ ANTHROPIC_API_KEY configured
  ✓ Google SDK            ℹ GOOGLE_API_KEY not set
  ✓ OpenAI SDK            ℹ OPENAI_API_KEY not set
  ℹ Ollama: not reachable at localhost:11434

Next steps
  • Add cloud keys:   parliament keys set <provider> <key>
  • Local models?     Install Ollama from https://ollama.com, then `ollama pull llama3.1`
  • Run the TUI:      parliament
```

### Sample output (broken install)

```
Environment
  ✗ Python 3.10.4 — please upgrade to ≥3.11
  ✓ Curses available
  ...

Install is not functional. Fix the items marked ✗ above.
$ echo $?
1
```

### Implementation outline

- New function `doctor()` in `src/parliament/cli.py`, registered with `@main.command()`.
- Reuses `load_keys()` from `parliament.config`. The key-status helper currently in `tui.py:_api_key_status` is extracted to `parliament/config.py` so both TUI and doctor share it.
- Ollama probe: `httpx.get("http://localhost:11434/api/tags", timeout=2.0)`.
- Curses check on Windows: `try: import curses; stdscr = curses.initscr(); curses.endwin()` inside `try/except`.
- Output via Rich `Console` (already a dep), using `[green]`, `[red]`, `[blue]`, `[yellow]` markup.

### Tests

New `tests/test_doctor.py`:
- Python version pass/fail (monkeypatch `sys.version_info`)
- Ollama reachable / unreachable (monkeypatch `httpx.get`)
- Key configured / not configured (monkeypatch env + `KEYS_FILE`)
- Curses-fail path on Windows (monkeypatch `curses.initscr` to raise)
- Exit code 0 on functional install (using `CliRunner`)
- Exit code 1 on Python-too-old install

Estimated implementation: ~120 lines doctor + ~80 lines tests.

## `pyproject.toml` changes

```toml
[project]
name = "llm-parliament"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "openai>=1.0",                                                # also covers Ollama via custom base_url
    "click>=8.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "anthropic>=0.40",                                            # was [cloud] extra → required
    "google-genai>=1.0",                                          # was [cloud] extra → required
    "httpx>=0.27",                                                # NEW — explicit; was transitive via openai
    "windows-curses>=2.4; platform_system == 'Windows'",
]

[project.optional-dependencies]
# anthropic / google / cloud / all extras REMOVED — those deps are now required.
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]

[project.scripts]
parliament = "parliament.cli:main"
```

No other manifest changes. Classifiers, license, urls, build-system stay as-is.

## PyPI release process

### One-time setup

1. Create PyPI account at <https://pypi.org/account/register/>.
2. Create API token at <https://pypi.org/manage/account/token/>. Scope: "Entire account" for first publish, narrow to project scope after first successful publish.
3. Configure twine via `~/.pypirc`:
   ```ini
   [pypi]
   username = __token__
   password = pypi-AgEIcHlwaS5vcmc...
   ```
4. Verify name `llm-parliament` is available on PyPI (visit <https://pypi.org/project/llm-parliament/> — should 404).
5. `pipx install build` and `pipx install twine`.

### Per-release workflow

```bash
# Bump version in pyproject.toml (only after 0.1.0).
python -m build              # creates dist/*.whl and dist/*.tar.gz
twine upload dist/*          # uploads to PyPI
git tag v0.1.0
git push origin v0.1.0

pipx install llm-parliament  # smoke test
parliament doctor
```

### v0.1.0 first-publish flow

For the first publish, do a TestPyPI rehearsal:

```bash
# Configure ~/.pypirc with [testpypi] section as well.
twine upload --repository testpypi dist/*
pipx install --pip-args "--index-url https://test.pypi.org/simple/" llm-parliament
parliament doctor
# If happy: twine upload dist/*  (real PyPI)
```

Subsequent releases skip TestPyPI.

### Documentation

`RELEASING.md` is added to the repo root with the same content as above (slightly more thorough). The README does not include release instructions — those are contributor knowledge, not user knowledge.

## Migration impact

- **Existing git-installed users:** `pip uninstall llm-parliament` (or `pipx uninstall`) → `pipx install llm-parliament`. `~/.parliament/` survives because it's outside the package install dir. Documented in a one-line note in the README.
- **Users with `llm-parliament[cloud]` in requirements files:** drop the `[cloud]` — the SDKs are now required. `pip` will warn but still resolve.
- **The `windows-fixes` branch on origin** can be deleted once 0.1.0 is published, completing the cleanup started during the Windows-Testing merge.

## Out of scope

Explicit non-goals to keep this focused:

- GitHub Actions for PyPI publish.
- `CONTRIBUTING.md` (current Development section in README is sufficient).
- Multi-language / i18n.
- Distribution via Homebrew / Chocolatey / apt — `pipx` is sufficient on all three OSes.
- Auto-update mechanism — `pipx upgrade` covers it.
- Install/doctor telemetry — explicit non-goal, never want this.

## Estimated scope

| Component | Files | LOC delta |
|---|---|---|
| `pyproject.toml` dep changes | 1 | ~10 |
| `parliament doctor` command | `cli.py` + new `tests/test_doctor.py` | ~120 + ~80 |
| README rewrite | `README.md` | ~80 net |
| New `RELEASING.md` | new file | ~50 |
| Total | ~5 files | ~250-300 lines net |

Existing 104 tests stay green throughout. New doctor tests bring total to ~110.
