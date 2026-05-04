# Install Routine + `parliament doctor` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship llm-parliament 0.1.0 to PyPI with a single canonical install path (`pipx install llm-parliament`), bundle cloud SDKs by default, add a `parliament doctor` health-check command, and rewrite README with per-OS install instructions.

**Architecture:** Doctor logic lives in a new module (`src/parliament/doctor.py`) and is invoked from a thin click command in `cli.py`. Shared `KEY_PROVIDERS` constant and `api_key_status()` helper move from `tui.py`/`cli.py` into `config.py` to avoid duplication and make them reusable by the doctor. Cloud SDKs (`anthropic`, `google-genai`) move from optional `[cloud]` extra into top-level `dependencies` so a single `pipx install` command works everywhere. README structure follows a 12-section layout with Quick Start + per-OS Installation blocks + new "Verify your install" section.

**Tech Stack:** Python 3.11+, click 8, rich 13, httpx (newly explicit), hatchling build backend, pytest + pytest-asyncio, twine + python-build for PyPI release.

**Spec source:** `docs/superpowers/specs/2026-05-04-install-routine-design.md` (commit 2892363).

**Branch:** `install-routine`. **Final delivery:** PR against `main`, mirroring PR #1 and PR #2 workflow.

---

## File Structure

### Files modified

| Path | Responsibility | Change |
|---|---|---|
| `pyproject.toml` | Package manifest | Bundle cloud SDKs, add explicit `httpx`, drop `[cloud]/[anthropic]/[google]/[all]` extras |
| `src/parliament/config.py` | Config + secrets I/O | Add `KEY_PROVIDERS` constant + `api_key_status()` helper |
| `src/parliament/tui.py` | Curses TUI | Replace local `KEY_PROVIDERS` and `_api_key_status` with imports from `config` |
| `src/parliament/cli.py` | Click commands + entry | Replace local `KEY_PROVIDERS` with import, add new `doctor` subcommand |
| `tests/test_config.py` | Existing config tests | Add tests for `api_key_status()` |
| `README.md` | User-facing docs | Rewrite Quick Start, Installation, add "Verify your install", drop stale `config.cloud.yaml` refs, mark Ollama as optional |

### Files created

| Path | Responsibility |
|---|---|
| `src/parliament/doctor.py` | All check functions (`_check_*`) + `run_doctor()` orchestrator |
| `tests/test_doctor.py` | Unit tests per check + e2e exit-code tests via `CliRunner` |
| `RELEASING.md` | Contributor docs for PyPI release workflow |

---

## Task 1: Set up feature branch and baseline

**Files:** None (git operations only).

- [ ] **Step 1.1: Verify clean working tree on main**

Run:
```bash
git status
```
Expected: `On branch main` and `nothing to commit, working tree clean`. If dirty, stop and resolve.

- [ ] **Step 1.2: Create feature branch off main**

Run:
```bash
git checkout -b install-routine
```
Expected: `Switched to a new branch 'install-routine'`.

- [ ] **Step 1.3: Run baseline test suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 104 passed (no failures, no errors).

- [ ] **Step 1.4: Confirm Python version is what we declare**

Run:
```bash
.venv/bin/python --version
```
Expected: `Python 3.12.x` or `3.11.x` or `3.13.x` (any ≥3.11).

No commit at this task — branch creation alone doesn't need one.

---

## Task 2: Extract `KEY_PROVIDERS` and `api_key_status` to `config.py`

**Files:**
- Modify: `src/parliament/config.py` (add constant + function)
- Modify: `src/parliament/tui.py:32-36` (drop local `KEY_PROVIDERS`), `tui.py:154-158` (drop local `_api_key_status`)
- Modify: `src/parliament/cli.py:28-32` (drop local `KEY_PROVIDERS`)
- Test: `tests/test_config.py` (add tests for new helper)

- [ ] **Step 2.1: Write the failing test in `tests/test_config.py`**

Append to `tests/test_config.py`:

```python
def test_key_providers_maps_provider_names_to_env_vars():
    from parliament.config import KEY_PROVIDERS

    assert KEY_PROVIDERS["anthropic"] == "ANTHROPIC_API_KEY"
    assert KEY_PROVIDERS["openai"] == "OPENAI_API_KEY"
    assert KEY_PROVIDERS["google"] == "GOOGLE_API_KEY"


def test_api_key_status_returns_configured_when_env_set(monkeypatch):
    from parliament.config import api_key_status

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert api_key_status("anthropic") == "configured"


def test_api_key_status_returns_missing_when_env_unset(monkeypatch):
    from parliament.config import api_key_status

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert api_key_status("anthropic") == "missing"


def test_api_key_status_returns_not_required_for_unknown_provider():
    from parliament.config import api_key_status

    assert api_key_status("ollama") == "not required"
    assert api_key_status("mock") == "not required"
```

- [ ] **Step 2.2: Run tests to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_config.py -v
```
Expected: 4 new tests fail with `ImportError` or `AttributeError` because `KEY_PROVIDERS` and `api_key_status` don't exist yet in `config.py`.

- [ ] **Step 2.3: Add `KEY_PROVIDERS` and `api_key_status()` to `config.py`**

In `src/parliament/config.py`, just below the existing `EXAMPLE_CONFIG = ...` line, add:

```python
KEY_PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def api_key_status(provider: str) -> str:
    """Return 'configured', 'missing', or 'not required' for a provider's API key."""
    env_var = KEY_PROVIDERS.get(provider)
    if env_var is None:
        return "not required"
    return "configured" if os.environ.get(env_var) else "missing"
```

- [ ] **Step 2.4: Run config tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_config.py -v
```
Expected: all tests in `test_config.py` pass (3 original + 4 new = 7 total).

- [ ] **Step 2.5: Replace local `KEY_PROVIDERS` and `_api_key_status` in `tui.py`**

In `src/parliament/tui.py`, find the import block starting around line 19 and update the import from `parliament.config` to include the new symbols:

```python
from parliament.config import (
    KEY_PROVIDERS,
    PARLIAMENT_DIR,
    USER_CONFIG,
    api_key_status,
    build_parliament_from_config,
    load_keys,
    save_config,
    save_key,
)
```

Then **delete** the local `KEY_PROVIDERS = {...}` block at line 32-36 and the local `def _api_key_status(...)` at line 154-158.

Replace the two callers:
- Line 121: `api_key_status=_api_key_status(member.provider_name),` → `api_key_status=api_key_status(member.provider_name),`
- Line 866: `("API key", _api_key_status(draft["provider"])),` → `("API key", api_key_status(draft["provider"])),`

- [ ] **Step 2.6: Replace local `KEY_PROVIDERS` in `cli.py`**

In `src/parliament/cli.py`, update the import block (around line 15-22) to include `KEY_PROVIDERS`:

```python
from parliament.config import (
    KEYS_FILE,
    KEY_PROVIDERS,
    build_parliament_from_config,
    load_config,
    load_keys,
    save_key,
    remove_key,
)
```

Then **delete** the local `KEY_PROVIDERS = {...}` block at line 28-32.

- [ ] **Step 2.7: Run full test suite to verify no regressions**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 108 passed (original 104 + 4 new = 108).

- [ ] **Step 2.8: Commit**

```bash
git add src/parliament/config.py src/parliament/tui.py src/parliament/cli.py tests/test_config.py
git commit -m "$(cat <<'EOF'
refactor: extract KEY_PROVIDERS and api_key_status to config.py

Both tui.py and cli.py had identical KEY_PROVIDERS dicts. The
api_key_status helper lived only in tui.py. The forthcoming `parliament
doctor` command needs the same logic, so consolidate to config.py.

- config.py: add KEY_PROVIDERS constant and api_key_status() function
- tui.py: import shared symbols, drop local copies
- cli.py: import shared KEY_PROVIDERS, drop local copy
- test_config.py: cover new api_key_status helper

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update `pyproject.toml` to bundle cloud SDKs and declare `httpx`

**Files:**
- Modify: `pyproject.toml:25-47`

- [ ] **Step 3.1: Edit `pyproject.toml` dependency block**

Replace lines 25-47 in `pyproject.toml` with:

```toml
dependencies = [
    "openai>=1.0",     # also covers Ollama via custom base_url
    "click>=8.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "anthropic>=0.40",
    "google-genai>=1.0",
    "httpx>=0.27",
    "windows-curses>=2.4; platform_system == 'Windows'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]
```

This drops `[anthropic]`, `[google]`, `[cloud]`, and `[all]` extras and promotes `anthropic`, `google-genai`, `httpx` to required.

- [ ] **Step 3.2: Reinstall the package to refresh deps**

Run:
```bash
.venv/bin/pip install -e ".[dev]" --quiet
```
Expected: clean install, no errors. Output may include "Successfully installed ..." for httpx if it wasn't pinned before.

- [ ] **Step 3.3: Verify imports of cloud SDKs and httpx work from the venv**

Run:
```bash
.venv/bin/python -c "import anthropic, google.genai, httpx; print('OK', anthropic.__version__, httpx.__version__)"
```
Expected: `OK <version> <version>` printed. If ImportError, the install failed.

- [ ] **Step 3.4: Run full test suite to verify nothing regressed**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 108 passed.

- [ ] **Step 3.5: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
build: bundle cloud SDKs as required deps; add explicit httpx

- Move anthropic and google-genai from [cloud] extra to required
  dependencies. Single install command (`pipx install llm-parliament`)
  now provides all providers; no [cloud] extra needed.
- Drop [anthropic], [google], [cloud], [all] optional-dependencies.
  Existing users with `llm-parliament[cloud]` in requirements will get
  a pip warning but the install still resolves.
- Add explicit httpx>=0.27 dep. It was already transitive via openai;
  making it explicit decouples us from openai's pinning and is needed
  by the forthcoming `parliament doctor` Ollama probe.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create `doctor` module skeleton and register click command

**Files:**
- Create: `src/parliament/doctor.py`
- Modify: `src/parliament/cli.py` (add `doctor` subcommand)
- Test: `tests/test_doctor.py` (new file)

- [ ] **Step 4.1: Write a failing skeleton test**

Create `tests/test_doctor.py` with:

```python
"""Health-check command tests."""

from __future__ import annotations

from click.testing import CliRunner


def test_doctor_command_runs_and_exits_zero_on_a_working_install(monkeypatch, tmp_path):
    """Bare smoke test: `parliament doctor` runs without crashing on a healthy box."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from parliament import cli

    result = CliRunner().invoke(cli.main, ["doctor"])

    # Skeleton phase: the command exists and exits 0 when there's nothing wrong.
    assert result.exit_code == 0, result.output
    assert "Environment" in result.output or "Doctor" in result.output
```

- [ ] **Step 4.2: Run test to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v
```
Expected: FAIL with `Error: No such command 'doctor'.` (click reports unknown command).

- [ ] **Step 4.3: Create `src/parliament/doctor.py` with skeleton orchestrator**

Create `src/parliament/doctor.py`:

```python
"""Health-check logic for `parliament doctor`."""

from __future__ import annotations

from rich.console import Console


def run_doctor(console: Console) -> int:
    """Run all doctor checks and print a report. Returns exit code (0 ok, 1 broken)."""
    console.print("[bold]Environment[/bold]")
    console.print("[bold]Providers[/bold]")
    console.print("[bold]Next steps[/bold]")
    return 0
```

- [ ] **Step 4.4: Register the click command in `cli.py`**

Append after the existing `keys_remove` command (around line 320, end of file) in `src/parliament/cli.py`:

```python
@main.command()
def doctor():
    """Run install health checks (Python version, providers, Ollama, etc.)."""
    from parliament.doctor import run_doctor

    exit_code = run_doctor(console)
    raise SystemExit(exit_code)
```

- [ ] **Step 4.5: Run skeleton test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v
```
Expected: PASS — the smoke test confirms the command exists, runs, prints "Environment", and exits 0.

- [ ] **Step 4.6: Manual smoke**

Run:
```bash
.venv/bin/parliament doctor
```
Expected: Three section headers printed (Environment, Providers, Next steps). No traceback. Exit code 0 (run `echo $?`).

- [ ] **Step 4.7: Run full suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 109 passed (108 + 1 new skeleton test).

- [ ] **Step 4.8: Commit**

```bash
git add src/parliament/doctor.py src/parliament/cli.py tests/test_doctor.py
git commit -m "$(cat <<'EOF'
feat: scaffold parliament doctor command

Adds a thin click subcommand `parliament doctor` that delegates to a
new `parliament.doctor` module. Currently only prints section
placeholders and exits 0. Subsequent commits flesh out the actual
checks (Python version, curses, terminal size, config, providers,
Ollama).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement environment checks (Python version, curses, terminal, config)

**Files:**
- Modify: `src/parliament/doctor.py` (add 4 check functions + integrate into `run_doctor`)
- Modify: `tests/test_doctor.py` (add tests per check)

- [ ] **Step 5.1: Write failing tests for the 4 environment checks**

Append to `tests/test_doctor.py`:

```python
def test_check_python_version_passes_on_supported_version(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr("sys.version_info", (3, 12, 5, "final", 0))
    result = doctor._check_python_version()

    assert result.ok is True
    assert "3.12.5" in result.message


def test_check_python_version_fails_on_too_old(monkeypatch):
    from parliament import doctor

    monkeypatch.setattr("sys.version_info", (3, 10, 4, "final", 0))
    result = doctor._check_python_version()

    assert result.ok is False
    assert "3.10.4" in result.message
    assert ">=3.11" in result.message or "3.11" in result.message


def test_check_curses_passes_when_curses_imports():
    from parliament import doctor

    result = doctor._check_curses()
    assert result.ok is True


def test_check_curses_fails_when_curses_unimportable(monkeypatch):
    from parliament import doctor
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "curses":
            raise ImportError("no curses on this box")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = doctor._check_curses()
    assert result.ok is False


def test_check_terminal_size_passes_on_large_enough(monkeypatch):
    from parliament import doctor
    import os

    monkeypatch.setattr(os, "get_terminal_size", lambda: os.terminal_size((142, 38)))
    result = doctor._check_terminal_size()

    assert result.ok is True
    assert "142" in result.message
    assert "38" in result.message


def test_check_terminal_size_warns_when_too_small(monkeypatch):
    from parliament import doctor
    import os

    monkeypatch.setattr(os, "get_terminal_size", lambda: os.terminal_size((60, 20)))
    result = doctor._check_terminal_size()

    # Terminal size is informational/warn — never a hard fail.
    assert result.ok is True
    assert result.warn is True


def test_check_config_passes_after_first_run(tmp_path, monkeypatch):
    from parliament import doctor
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    import importlib
    import parliament.config
    importlib.reload(parliament.config)
    importlib.reload(doctor)

    # load_config triggers first-run copy of example
    parliament.config.load_config()

    result = doctor._check_config()
    assert result.ok is True
    assert ".parliament/config.yaml" in result.message
```

- [ ] **Step 5.2: Run new tests to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v
```
Expected: 7 new tests fail with `AttributeError: module 'parliament.doctor' has no attribute '_check_*'`.

- [ ] **Step 5.3: Implement the 4 environment check functions plus `CheckResult`**

Replace the entire content of `src/parliament/doctor.py` with:

```python
"""Health-check logic for `parliament doctor`."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from rich.console import Console


@dataclass
class CheckResult:
    """Outcome of a single doctor check."""
    ok: bool                # False → fail (exit 1) unless `warn` is True
    warn: bool = False      # True → ok=True but render in yellow
    info: bool = False      # True → ok=True but render in blue (e.g. "key not set")
    message: str = ""       # what to render after the symbol


def _check_python_version() -> CheckResult:
    # Use index access (works with both real version_info and test plain tuples)
    v = sys.version_info
    actual = f"{v[0]}.{v[1]}.{v[2]}"
    if (v[0], v[1]) >= (3, 11):
        return CheckResult(ok=True, message=f"Python {actual} (>=3.11 required)")
    return CheckResult(
        ok=False,
        message=f"Python {actual} - please upgrade to >=3.11",
    )


def _check_curses() -> CheckResult:
    try:
        import curses  # noqa: F401
        return CheckResult(ok=True, message="Curses available")
    except ImportError as e:
        return CheckResult(ok=False, message=f"Curses unavailable: {e}")


def _check_terminal_size() -> CheckResult:
    try:
        size = os.get_terminal_size()
    except OSError:
        return CheckResult(ok=True, warn=True, message="Terminal size unknown (not a TTY)")
    msg = f"Terminal: {size.columns}x{size.lines}"
    if size.columns >= 80 and size.lines >= 24:
        return CheckResult(ok=True, message=msg)
    return CheckResult(ok=True, warn=True, message=f"{msg} (recommended >=80x24)")


def _check_config() -> CheckResult:
    from parliament.config import USER_CONFIG, load_config

    load_config()  # triggers first-run copy if needed
    return CheckResult(
        ok=True,
        message=f"Config: {USER_CONFIG} (initialized)",
    )


def run_doctor(console: Console) -> int:
    """Run all doctor checks and print a report. Returns exit code (0 ok, 1 broken)."""
    env_checks = [
        _check_python_version(),
        _check_curses(),
        _check_terminal_size(),
        _check_config(),
    ]

    console.print("[bold]Environment[/bold]")
    for r in env_checks:
        symbol, color = _symbol_for(r)
        console.print(f"  [{color}]{symbol}[/{color}] {r.message}")

    console.print("[bold]Providers[/bold]")
    console.print("[bold]Next steps[/bold]")

    has_failure = any((not r.ok) for r in env_checks)
    return 1 if has_failure else 0


def _symbol_for(r: CheckResult) -> tuple[str, str]:
    """Map a CheckResult to (unicode-symbol, rich-color)."""
    if not r.ok:
        return ("✗", "red")        # ✗
    if r.warn:
        return ("!", "yellow")
    if r.info:
        return ("ℹ", "blue")       # ℹ
    return ("✓", "green")          # ✓
```

- [ ] **Step 5.4: Run tests to verify environment checks pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v
```
Expected: all 8 tests pass (1 skeleton + 7 new = 8 total in test_doctor.py).

- [ ] **Step 5.5: Manual smoke**

Run:
```bash
.venv/bin/parliament doctor
```
Expected: Environment section now prints 4 checks with green ✓ symbols (or yellow if your terminal is small). Providers and Next steps still empty. Exit 0.

- [ ] **Step 5.6: Run full suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 116 passed (109 + 7 new = 116).

- [ ] **Step 5.7: Commit**

```bash
git add src/parliament/doctor.py tests/test_doctor.py
git commit -m "$(cat <<'EOF'
feat(doctor): add environment checks (python, curses, terminal, config)

Doctor now reports Python version, curses availability, terminal size,
and config initialization. CheckResult dataclass carries ok/warn/info
flags so the renderer can pick the right symbol and color (green/red/
yellow/blue). Python <3.11 and curses ImportError are hard failures
(exit 1); terminal size below 80x24 is a warning.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement provider checks (cloud SDKs + API keys)

**Files:**
- Modify: `src/parliament/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 6.1: Write failing tests for provider checks**

Append to `tests/test_doctor.py`:

```python
def test_check_provider_returns_both_ok_when_sdk_imports_and_key_set(monkeypatch):
    from parliament import doctor

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sdk_result, key_result = doctor._check_provider("anthropic")

    assert sdk_result.ok is True
    assert "Anthropic SDK" in sdk_result.message
    assert key_result.ok is True
    assert key_result.info is False
    assert "configured" in key_result.message


def test_check_provider_returns_info_when_key_missing(monkeypatch):
    from parliament import doctor

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, key_result = doctor._check_provider("anthropic")

    assert key_result.ok is True
    assert key_result.info is True
    assert "not set" in key_result.message


def test_check_provider_fails_when_sdk_unimportable(monkeypatch):
    from parliament import doctor
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sdk_result, _ = doctor._check_provider("anthropic")

    assert sdk_result.ok is False
    assert "SDK" in sdk_result.message
```

- [ ] **Step 6.2: Run tests to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py::test_check_provider -v
```
Expected: 3 tests fail with AttributeError on `_check_provider`.

- [ ] **Step 6.3: Add `_check_provider` and integrate into `run_doctor`**

In `src/parliament/doctor.py`, add this after `_check_config`:

```python
PROVIDER_DISPLAY = {
    "anthropic": ("Anthropic SDK", "anthropic"),
    "google": ("Google SDK", "google.genai"),
    "openai": ("OpenAI SDK", "openai"),
}


def _check_provider(provider: str) -> tuple[CheckResult, CheckResult]:
    """Return (sdk_result, key_result) for one cloud provider."""
    from parliament.config import KEY_PROVIDERS, api_key_status

    display_name, import_name = PROVIDER_DISPLAY[provider]

    # SDK check
    try:
        __import__(import_name)
        sdk_result = CheckResult(ok=True, message=display_name)
    except ImportError as e:
        sdk_result = CheckResult(ok=False, message=f"{display_name} not installed: {e}")

    # Key check
    env_var = KEY_PROVIDERS[provider]
    status = api_key_status(provider)
    if status == "configured":
        key_result = CheckResult(ok=True, message=f"{env_var} configured")
    else:
        key_result = CheckResult(ok=True, info=True, message=f"{env_var} not set")

    return sdk_result, key_result
```

Update `run_doctor` to populate the Providers section. Replace the existing `console.print("[bold]Providers[/bold]")` line and the empty Next-steps line with:

```python
    console.print("[bold]Providers[/bold]")
    provider_checks: list[CheckResult] = []
    for provider in ("anthropic", "google", "openai"):
        sdk_r, key_r = _check_provider(provider)
        provider_checks.extend([sdk_r, key_r])
        sdk_sym, sdk_col = _symbol_for(sdk_r)
        key_sym, key_col = _symbol_for(key_r)
        console.print(
            f"  [{sdk_col}]{sdk_sym}[/{sdk_col}] {sdk_r.message:<20} "
            f"[{key_col}]{key_sym}[/{key_col}] {key_r.message}"
        )

    console.print("[bold]Next steps[/bold]")

    all_checks = env_checks + provider_checks
    has_failure = any((not r.ok) for r in all_checks)
    return 1 if has_failure else 0
```

(Delete the old `has_failure = any(...)` line that was based on `env_checks` only.)

- [ ] **Step 6.4: Run provider tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py::test_check_provider -v
```
Expected: 3 tests pass.

- [ ] **Step 6.5: Manual smoke**

Run:
```bash
.venv/bin/parliament doctor
```
Expected: Providers section now prints 3 lines like:
```
  ✓ Anthropic SDK         ℹ ANTHROPIC_API_KEY not set
  ✓ Google SDK            ℹ GOOGLE_API_KEY not set
  ✓ OpenAI SDK            ℹ OPENAI_API_KEY not set
```

- [ ] **Step 6.6: Run full suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 119 passed (116 + 3 new).

- [ ] **Step 6.7: Commit**

```bash
git add src/parliament/doctor.py tests/test_doctor.py
git commit -m "$(cat <<'EOF'
feat(doctor): add cloud provider checks (SDK + API key)

For each of anthropic, google, openai: confirm SDK importable and
report whether the corresponding env var is set. Missing keys are
informational (blue), not failures - the tool runs fine on mocks
alone. SDK-not-importable IS a failure since cloud SDKs are now
required deps after this release.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement Ollama probe

**Files:**
- Modify: `src/parliament/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 7.1: Write failing tests for Ollama probe**

Append to `tests/test_doctor.py`:

```python
def test_check_ollama_reports_reachable_with_model_count(monkeypatch):
    from parliament import doctor
    import httpx

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"models": [{"name": "llama3.1:latest"}, {"name": "deepseek-r1:8b"}]}

    def fake_get(url, timeout=None):
        assert "11434" in url
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True
    assert result.info is False
    assert "2 model" in result.message  # "2 models" or "2 model(s)"


def test_check_ollama_reports_unreachable_as_info_not_failure(monkeypatch):
    from parliament import doctor
    import httpx

    def fake_get(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True       # informational, not failure
    assert result.info is True
    assert "not reachable" in result.message


def test_check_ollama_treats_timeout_as_unreachable(monkeypatch):
    from parliament import doctor
    import httpx

    def fake_get(url, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = doctor._check_ollama()
    assert result.ok is True
    assert result.info is True
```

- [ ] **Step 7.2: Run tests to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py::test_check_ollama -v
```
Expected: 3 tests fail with AttributeError on `_check_ollama`.

- [ ] **Step 7.3: Implement `_check_ollama` and wire into `run_doctor`**

In `src/parliament/doctor.py`, add the import at the top:

```python
import httpx
```

Add this function after `_check_provider`:

```python
def _check_ollama(base_url: str = "http://localhost:11434") -> CheckResult:
    """Probe the Ollama daemon. Unreachable is informational, not a failure."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return CheckResult(
                ok=True,
                message=f"Ollama: reachable, {len(models)} model(s) installed",
            )
        return CheckResult(
            ok=True,
            info=True,
            message=f"Ollama: unexpected status {response.status_code}",
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return CheckResult(
            ok=True,
            info=True,
            message=f"Ollama: not reachable at {base_url}",
        )
```

In `run_doctor`, just before `console.print("[bold]Next steps[/bold]")`, add the Ollama line:

```python
    ollama_result = _check_ollama()
    sym, col = _symbol_for(ollama_result)
    console.print(f"  [{col}]{sym}[/{col}] {ollama_result.message}")
```

And include `ollama_result` in `all_checks`:

```python
    all_checks = env_checks + provider_checks + [ollama_result]
```

- [ ] **Step 7.4: Run Ollama tests to verify pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py::test_check_ollama -v
```
Expected: 3 tests pass.

- [ ] **Step 7.5: Manual smoke**

Run:
```bash
.venv/bin/parliament doctor
```
Expected: Providers section now ends with an Ollama line. If Ollama is running locally, it will say "reachable, N model(s) installed"; if not, "not reachable at http://localhost:11434".

- [ ] **Step 7.6: Run full suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 122 passed (119 + 3 new).

- [ ] **Step 7.7: Commit**

```bash
git add src/parliament/doctor.py tests/test_doctor.py
git commit -m "$(cat <<'EOF'
feat(doctor): probe Ollama daemon at localhost:11434

Reports Ollama reachability and installed-model count via the
/api/tags endpoint with a 2-second timeout. Unreachable is
informational (blue), not a failure - many users run cloud-only.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Render Next-steps and finalize exit-code semantics

**Files:**
- Modify: `src/parliament/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 8.1: Write failing tests for "Next steps" rendering and exit codes**

Append to `tests/test_doctor.py`:

```python
def test_doctor_exit_code_is_one_when_python_too_old(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.version_info", (3, 10, 4, "final", 0))

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 1
    assert "not functional" in result.output.lower() or "fix" in result.output.lower()


def test_doctor_exit_code_is_zero_when_only_optional_items_missing(monkeypatch, tmp_path):
    """No keys, no Ollama → still exit 0 (mock works fine)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    import httpx
    def unreachable(url, timeout=None):
        raise httpx.ConnectError("no ollama")
    monkeypatch.setattr(httpx, "get", unreachable)

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert result.exit_code == 0


def test_doctor_next_steps_mentions_keys_and_ollama_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    import httpx
    def unreachable(url, timeout=None):
        raise httpx.ConnectError("no ollama")
    monkeypatch.setattr(httpx, "get", unreachable)

    from parliament import cli
    result = CliRunner().invoke(cli.main, ["doctor"])

    assert "parliament keys set" in result.output
    assert "ollama.com" in result.output.lower() or "ollama" in result.output.lower()
```

- [ ] **Step 8.2: Run tests to verify failure**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v -k "exit_code or next_steps"
```
Expected: 3 tests fail (broken-install message missing, or "Next steps" content missing).

- [ ] **Step 8.3: Update `run_doctor` to render Next steps and a broken-install footer**

Replace the `Next steps` rendering block in `run_doctor` (the part after the Ollama line and before `all_checks`) with:

```python
    console.print("[bold]Next steps[/bold]")
    cloud_keys_missing = any(r.info for r in provider_checks)
    if cloud_keys_missing:
        console.print("  - Add cloud keys:   parliament keys set <provider> <key>")
    if ollama_result.info:
        console.print(
            "  - Local models?     Install Ollama from https://ollama.com, "
            "then `ollama pull llama3.1`"
        )
    console.print("  - Run the TUI:      parliament")

    all_checks = env_checks + provider_checks + [ollama_result]
    has_failure = any((not r.ok) for r in all_checks)
    if has_failure:
        console.print()
        console.print("[red]Install is not functional. Fix the items marked with the failure symbol above.[/red]")
        return 1
    return 0
```

- [ ] **Step 8.4: Run all doctor tests to verify pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_doctor.py -v
```
Expected: all tests pass (1 skeleton + 7 env + 3 provider + 3 ollama + 3 exit/next = 17 total in test_doctor.py).

- [ ] **Step 8.5: Manual smoke — full doctor output**

Run:
```bash
.venv/bin/parliament doctor
echo "exit: $?"
```
Expected: full report rendered (Environment, Providers with all 3 SDKs, Ollama line, Next steps with relevant suggestions). Exit `0` on a healthy install. Note: the broken-install path (Python too old) is covered by the unit test in Step 8.1; manually downgrading Python locally to test it isn't worth doing.

- [ ] **Step 8.6: Run full suite**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 125 passed (122 + 3 new).

- [ ] **Step 8.7: Commit**

```bash
git add src/parliament/doctor.py tests/test_doctor.py
git commit -m "$(cat <<'EOF'
feat(doctor): render Next steps and finalize exit codes

- Next steps section dynamically suggests `parliament keys set` if any
  cloud key is missing, and the Ollama install link if Ollama is not
  reachable. Always points to `parliament` as the entry to the TUI.
- Exit code 1 only on hard failures (Python too old, curses can't
  import). Missing keys and missing Ollama are informational and exit 0.
- Broken-install footer printed in red when exit code is 1, guiding
  users to the failed checks.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Rewrite README

**Files:**
- Modify: `README.md` (full rewrite of sections 2-8 per spec; sections 1, 9-12 unchanged)

- [ ] **Step 9.1: Replace the Quick Start section**

Find lines 12-23 in `README.md` (the existing Quick Start block) and replace with:

```markdown
## Quick Start

```bash
pipx install llm-parliament
parliament doctor
parliament              # opens the TUI
```

The mock parliament runs out of the box with no setup.
```

- [ ] **Step 9.2: Replace the Installation section**

Find the existing `## Installation` section (around lines 25-57) and replace with:

```markdown
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
```

- [ ] **Step 9.3: Add the "Verify your install" section**

Insert this section between Installation and Configuration:

```markdown
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

Exit code is `0` if the install is functional (regardless of whether you have keys/Ollama configured), or `1` if something is broken (e.g. Python too old).
```

- [ ] **Step 9.4: Rewrite the Local Models section as "Optional"**

Replace the existing `## Local Models` section with:

```markdown
## Optional: Local Models (Ollama)

Ollama runs LLMs locally — free, private, no API keys. Install it separately, then point a parliament member at it.

1. Install Ollama from <https://ollama.com> and start the daemon.
2. Pull a model:
   ```bash
   ollama pull llama3.1
   ```
3. Edit `~/.parliament/config.yaml` (or use the TUI) to add an Ollama member:
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

> **Note:** All providers default to no timeout (`timeout: null`), so a slow local model on modest hardware won't be cut off. If you want a hard limit, set `timeout: 600.0` on the relevant `providers.<name>` block.
```

- [ ] **Step 9.5: Update Cloud Models section to drop `config.cloud.yaml`**

Replace the existing `## Cloud Models` section with:

```markdown
## Optional: Cloud Models

To use Anthropic, Google, or OpenAI, set the corresponding API key:

```bash
parliament keys set anthropic sk-ant-...
parliament keys set google ...
parliament keys set openai sk-...
```

Then edit `~/.parliament/config.yaml` (or use the TUI) to add cloud members:

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

Keys are stored in `~/.parliament/keys.env` with `chmod 0600` on Unix. You
can also export `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GOOGLE_API_KEY`
directly in your environment if you prefer.

Useful key commands:

```bash
parliament keys list
parliament keys remove openai
```
```

- [ ] **Step 9.6: Add `parliament doctor` to the CLI Usage examples**

In the `## CLI Usage` section, find the code block around line 135 and add this line near the top of the block (after the `--mock` example):

```bash
# Check that the install is healthy
parliament doctor
```

- [ ] **Step 9.7: Manual review of the rewritten README**

Run:
```bash
grep -n "config.cloud.yaml\|config.mixed.yaml" README.md
```
Expected: no output. (All stale references gone.)

Run:
```bash
grep -n "pipx install llm-parliament" README.md
```
Expected: at least 4 hits (Quick Start + 3 OS blocks).

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 125 passed (no regressions from README changes — they don't touch code).

- [ ] **Step 9.8: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): rewrite install section with per-OS prereq blocks

- Quick Start trimmed to 3 commands (pipx install, doctor, parliament).
- Installation section now has 3 OS blocks (Linux, macOS, Windows) each
  ending in identical `pipx install llm-parliament` + `parliament doctor`
  for visual symmetry.
- New "Verify your install" section explains parliament doctor output.
- Local Models section reframed as "Optional: Local Models (Ollama)";
  default config is mock-only, so Ollama is no longer the default path.
- Cloud Models section reframed as "Optional: Cloud Models"; drops the
  stale `--config config.cloud.yaml` references (file no longer exists).
- CLI Usage examples include `parliament doctor`.
- Notes capture: bundled cloud SDKs, Windows Terminal recommendation,
  no-timeout default, key storage location.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Add `RELEASING.md`

**Files:**
- Create: `RELEASING.md`

- [ ] **Step 10.1: Create `RELEASING.md` with the full release workflow**

Create `RELEASING.md` in the repo root with:

````markdown
# Releasing llm-parliament

This document describes how to publish a new version of `llm-parliament` to PyPI.

## One-time setup

1. **Create a PyPI account** at <https://pypi.org/account/register/>.

2. **Create an API token** at <https://pypi.org/manage/account/token/>.
   - Scope: "Entire account" for the first publish.
   - Narrow to project scope (`Project: llm-parliament`) after the first successful publish.
   - Save the token — you only see it once.

3. **Configure twine** by creating `~/.pypirc`:

   ```ini
   [pypi]
   username = __token__
   password = pypi-AgEIcHlwaS5vcmc...   # the full token, including the `pypi-` prefix

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-AgEIcHRlc3RweXBpLm9yZw...   # separate TestPyPI token
   ```

4. **Verify the package name is available** on PyPI by visiting
   <https://pypi.org/project/llm-parliament/> — it should 404 before the
   first publish.

5. **Install build tools globally** (one-time):

   ```bash
   pipx install build
   pipx install twine
   ```

## First publish (v0.1.0)

For the very first publish, do a TestPyPI rehearsal so any metadata or
classifier issues surface before they hit real PyPI (where you cannot
overwrite versions).

```bash
# Standing on main, all changes merged, all tests green.

# Build wheel + sdist
python -m build

# Validate metadata
twine check dist/*

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Smoke-test the install from TestPyPI
pipx install \
  --pip-args "--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/" \
  llm-parliament
parliament doctor
pipx uninstall llm-parliament

# Happy? Real upload:
twine upload dist/*

# Tag the release
git tag v0.1.0
git push origin v0.1.0

# Verify
pipx install llm-parliament
parliament doctor
```

## Subsequent releases

Skip TestPyPI rehearsal for non-major releases.

```bash
# Bump version in pyproject.toml (semver: major.minor.patch).
# Commit the bump:
git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"

# Build, check, upload
python -m build
twine check dist/*
twine upload dist/*

# Tag and push
git tag vX.Y.Z
git push origin main vX.Y.Z

# Smoke
pipx install --upgrade llm-parliament
parliament doctor
```

## What can break and how to recover

- **Name conflict on first publish:** PyPI returns `400 File already exists`
  if `llm-parliament` is taken. Pick a different name in `pyproject.toml` and
  redo from the build step.
- **Metadata error:** `twine check` will catch most. Read the error, fix
  classifiers / license / readme rendering, re-run `python -m build`.
- **Bug in published version:** PyPI does not allow overwriting an
  existing version. You can only **yank** a version (hides it from new
  installs but doesn't delete it) and publish a patch. Yank via the PyPI
  web UI under "Manage project → Releases".
- **Wrong file in `dist/`:** delete the `dist/` directory and rebuild.

## Notes

- We do **not** use GitHub Actions for publishing right now. Manual local
  release is sufficient for a solo project. Revisit if release frequency
  grows or if multiple maintainers join.
- The `dist/` directory is gitignored — never commit build artifacts.
- `~/.pypirc` contains live tokens. Keep it `chmod 0600` and never commit
  it to any repo.
````

- [ ] **Step 10.2: Verify the file is in place and renders sanely**

Run:
```bash
head -30 RELEASING.md && echo "---" && wc -l RELEASING.md
```
Expected: file exists, ~80-100 lines.

- [ ] **Step 10.3: Run full suite (sanity)**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 125 passed.

- [ ] **Step 10.4: Commit**

```bash
git add RELEASING.md
git commit -m "$(cat <<'EOF'
docs: add RELEASING.md with PyPI publish workflow

Documents the manual release process: one-time PyPI account + token +
twine config, TestPyPI rehearsal for v0.1.0, per-release build/upload/
tag workflow, and recovery paths for common errors. Not in user-facing
README — release procedure is contributor knowledge only.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Final smoke and build verification

**Files:** None modified — verification only.

- [ ] **Step 11.1: Run the full test suite one more time**

Run:
```bash
.venv/bin/python -m pytest -q
```
Expected: 125 passed.

- [ ] **Step 11.2: Verify the package builds cleanly**

Run:
```bash
.venv/bin/python -m pip install --quiet build
rm -rf dist/
.venv/bin/python -m build 2>&1 | tail -10
```
Expected: `dist/` contains `llm_parliament-0.1.0.tar.gz` and `llm_parliament-0.1.0-py3-none-any.whl`. No errors.

- [ ] **Step 11.3: Validate package metadata with twine**

Run:
```bash
.venv/bin/python -m pip install --quiet twine
.venv/bin/python -m twine check dist/*
```
Expected: `PASSED` for both files.

- [ ] **Step 11.4: Run `parliament doctor` manually**

Run:
```bash
.venv/bin/parliament doctor
echo "exit code: $?"
```
Expected: full doctor output rendered (Environment, Providers, Next steps), exit 0 (assuming current Linux box has Python 3.11+).

- [ ] **Step 11.5: Verify the bare `parliament` command still launches the TUI**

Run:
```bash
timeout 2 .venv/bin/parliament; true
```
Expected: TUI starts (curses screen flashes briefly), then 2-second timeout kills it. Exit code 124 (from `timeout`), which is fine — the point is it didn't crash on launch.

- [ ] **Step 11.6: Clean up `dist/` (gitignored, but tidy)**

Run:
```bash
rm -rf dist/
```

No commit at this task — verification only.

---

## Task 12: Push branch and open PR

**Files:** None modified — git operations only.

- [ ] **Step 12.1: Sanity check current branch state**

Run:
```bash
git status && echo "---" && git log --oneline main..HEAD
```
Expected: working tree clean. Log shows the 9 commits added on `install-routine`:
1. refactor: extract KEY_PROVIDERS and api_key_status to config.py
2. build: bundle cloud SDKs as required deps; add explicit httpx
3. feat: scaffold parliament doctor command
4. feat(doctor): add environment checks
5. feat(doctor): add cloud provider checks
6. feat(doctor): probe Ollama daemon
7. feat(doctor): render Next steps and finalize exit codes
8. docs(readme): rewrite install section with per-OS prereq blocks
9. docs: add RELEASING.md with PyPI publish workflow

- [ ] **Step 12.2: Push branch to origin**

Run:
```bash
git push -u origin install-routine
```
Expected: branch published, output ends with `branch 'install-routine' set up to track 'origin/install-routine'`.

- [ ] **Step 12.3: Open PR on GitHub**

Run:
```bash
gh pr create --base main --head install-routine --title "Install routine + parliament doctor + PyPI release prep" --body "$(cat <<'EOF'
## Summary

Implements the design spec at `docs/superpowers/specs/2026-05-04-install-routine-design.md`.

- Adds `parliament doctor` health-check subcommand (Python version, curses, terminal size, config, cloud SDKs/keys, Ollama probe).
- Bundles `anthropic` and `google-genai` as required deps; drops the `[cloud]` extra.
- Adds explicit `httpx>=0.27` (was transitive via openai); doctor uses it for the Ollama probe.
- Rewrites the README install section with per-OS prereq one-liners (Linux, macOS, Windows).
- Adds `RELEASING.md` documenting the PyPI publish workflow.
- Extracts `KEY_PROVIDERS` and `api_key_status()` to `config.py` so doctor and TUI share them.

## How a new user is affected

Install becomes one canonical command on every OS:

```
pipx install llm-parliament
parliament doctor
parliament
```

The doctor command tells the user exactly what's working, what's optional (keys/Ollama), and what's broken. No traceback-spelunking on first run.

## Breaking changes

- The `[cloud]`, `[anthropic]`, `[google]`, `[all]` optional extras are removed. Anyone with `llm-parliament[cloud]` in a requirements file should drop the bracket. `pip` will warn but still resolve.
- This is the package's first PyPI publish at 0.1.0.

## Test plan

- [x] All 125 tests pass (104 original + 21 new across `test_config.py`, `test_doctor.py`).
- [x] `python -m build` produces clean wheel + sdist.
- [x] `twine check dist/*` passes.
- [x] `parliament doctor` runs cleanly on this Linux box.
- [x] Bare `parliament` still opens the TUI.
- [ ] Reviewer: smoke `parliament doctor` on Windows after install.
- [ ] After merge: follow `RELEASING.md` to publish to PyPI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed (e.g., `https://github.com/elarmuzik1993/llm-parliament/pull/3`).

- [ ] **Step 12.4: Capture PR URL for the user**

Print the URL printed by `gh pr create` and remind the user that:
- This branch is ready to review and merge.
- After merge, the next step is a manual PyPI publish following `RELEASING.md`.

---

## Self-review summary

Spec coverage (each row maps to a task that implements it):

| Spec section | Implemented in |
|---|---|
| Decision 1 (PyPI publish) | Tasks 3, 10, 11 (build/upload preparation) |
| Decision 2 (`parliament doctor`) | Tasks 4-8 |
| Decision 3 (per-OS prereqs in README) | Task 9 |
| Decision 4 (bundle cloud SDKs) | Task 3 |
| Decision 5 (no installer script) | n/a — explicit non-decision |
| Decision 6 (12-section README) | Task 9 |
| Decision 7 (`✓ ✗ ℹ` symbols) | Task 5 (`_symbol_for`) |
| Decision 8 (no network probe for keys) | Task 6 (only checks env presence) |
| Decision 9 (no auto-doctor on TUI launch) | n/a — non-decision |
| Decision 10 (explicit `httpx` dep) | Task 3 |
| Decision 11 (version 0.1.0 first publish) | Task 3 (no version bump) |
| Decision 12 (manual local release) | Task 10 (`RELEASING.md`) |
| Decision 13 (`RELEASING.md` exists) | Task 10 |
| Decision 14 (no GitHub Actions) | n/a — non-decision |
| Doctor checks 1-6 | Tasks 5 (env), 6 (providers), 7 (ollama) |
| Sample output formatting | Task 8 (Next steps + footer) |
| pyproject.toml diff | Task 3 |
| Migration impact (existing users) | Task 9 (README notes) |

No placeholders. No "TBD" / "TODO" / "implement later" / "fill in details" anywhere. Every step contains the actual code or command.

Type/name consistency: `CheckResult` dataclass introduced Task 5, used in Tasks 6, 7, 8. `_symbol_for` introduced Task 5, called in Tasks 6, 7. `KEY_PROVIDERS` and `api_key_status` introduced Task 2, used in Tasks 6 and indirectly via TUI.

Ordering: each task's tests pass on completion; full suite stays green between tasks. Tasks 5-8 build incrementally on the doctor module without breaking earlier tests.
