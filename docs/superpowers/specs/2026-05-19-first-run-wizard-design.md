# First-Run Config Wizard — Design

**Linear:** [USE-20](https://linear.app/user044/issue/USE-20/first-run-config-wizard-guide-users-to-working-model-setup)
**Status:** Approved (design); implementation pending
**Date:** 2026-05-19

---

## Problem

`_ensure_user_config()` currently copies `config.example.yaml` (3× mock providers) verbatim to `~/.parliament/config.yaml` on first run. Result:

- A fresh user with an `ANTHROPIC_API_KEY` already exported still gets a mock-only config and has to hand-edit YAML before getting real output.
- A user with only Ollama installed gets the same mock config; nothing surfaces which local models would actually fit their RAM.
- `parliament doctor` reports SDK presence and key presence but never reads the config to check whether the *configured* members are viable.

USE-20 acceptance criteria:

1. Fresh install with Anthropic key → config uses Claude automatically.
2. Fresh install with Ollama only → config uses models that fit detected RAM.
3. `parliament doctor` shows a warning if any member model is likely to OOM.

---

## Goals

- Replace the silent `shutil.copyfile` first-run path with an environment-aware wizard.
- Interactive when stdin/stdout are TTYs; auto-pick the detected preset silently otherwise (so `parliament ask "…" | tee out.txt` keeps working).
- Add a Members section to `parliament doctor` that cross-references configured members against installed Ollama models and system RAM.
- Centralise "what does a sensible 3-member parliament look like for environment X?" in a single module so we can update model defaults in one place.

## Non-goals

- No inline API-key entry in the wizard. Users still set keys via `parliament keys set <provider> <key>` or env vars.
- No inline `ollama pull` from the wizard. We *suggest* a pull command in the summary when the local-safe preset isn't viable; we don't run it.
- No `parliament init` command for re-triggering the wizard later. (Possible follow-up — explicitly out of scope here.)
- No member-by-member picker in the wizard. The TUI member-editor stays the place for fine-grained editing.

---

## Architecture

```
parliament <any command>
  │
  └─ load_config()
       │
       └─ _ensure_user_config()
            │
            ├─ if USER_CONFIG missing:
            │     run_first_run_wizard(USER_CONFIG)
            │       │
            │       ├─ env = detect_environment()
            │       ├─ preset = select_preset(env)
            │       ├─ if TTY:  Rich prompt, [Y/n]
            │       │           Y → write preset.config
            │       │           n or EOF → write mock preset
            │       │  else:    write preset.config silently,
            │       │           one-line notice to stderr
            │       └─ on write failure: fall back to
            │          shutil.copyfile(EXAMPLE_CONFIG, USER_CONFIG)
            │
            └─ return USER_CONFIG
```

### Modules

| Module | Status | Responsibility |
|---|---|---|
| `src/parliament/first_run.py` | new | `Environment` dataclass; `detect_environment()`; `run_first_run_wizard()`; Rich-based confirmation prompt. |
| `src/parliament/presets.py` | new | `Preset` dataclass; `select_preset(env) -> Preset`; one `build_<preset>(env)` function per preset; model-name constants at the top. |
| `src/parliament/config.py` | modified | `_ensure_user_config()` calls `run_first_run_wizard()` instead of `shutil.copyfile`. `_ensure_user_config()` owns the example-config fallback if the wizard raises. |
| `src/parliament/model_catalog.py` | modified | `fetch_ollama_models()` returns `OllamaModel` detail records via a new `PickerData.ollama_models` field. Backward-compat: `PickerData.models` still returns the name list. |
| `src/parliament/doctor.py` | modified | New `_check_member_viability()` rendered under a new `Members` heading. |
| `pyproject.toml` | modified | Adds `psutil` to runtime dependencies. |

### Data shapes

```python
# model_catalog.py

@dataclass(frozen=True)
class OllamaModel:
    name: str
    size_bytes: int

# first_run.py

@dataclass(frozen=True)
class Environment:
    anthropic_key: bool
    openai_key: bool
    google_key: bool
    ollama_reachable: bool
    ollama_models: tuple[OllamaModel, ...]
    total_ram_bytes: int | None   # None when psutil unavailable

# presets.py

@dataclass(frozen=True)
class Preset:
    name: str                     # e.g. "mixed", "cloud-anthropic"
    summary: str                  # human-readable one-liner shown in the wizard
    config: dict[str, Any]        # full YAML-serialisable config dict, including
                                  # display.show_debate + hansard.level defaults
    notice: str | None = None     # e.g. "Install at least 3 local models, …"
```

---

## Preset selection rules

Eight presets, first match wins:

| # | Trigger | Preset name | Members |
|---|---|---|---|
| 1 | Anthropic + OpenAI + Google keys all set | `cloud-full` | Claude (anthropic / claude-sonnet-4-6), GPT (openai / gpt-4o-mini), Gemini (google / gemini-2.5-flash) |
| 2 | Anthropic + Google keys, no OpenAI | `cloud-anthropic-google` | Claude (sonnet), Claude (haiku), Gemini (flash) |
| 3 | Anthropic + OpenAI keys, no Google | `cloud-anthropic-openai` | Claude (sonnet), Claude (haiku), GPT (4o-mini) |
| 4 | Any single cloud key + Ollama reachable with ≥2 installed models that fit RAM | `mixed` | 1× top model of that cloud, 2× smallest installed Ollama models that fit |
| 5 | Single cloud key, no usable Ollama | `cloud-anthropic` / `cloud-google` / `cloud-openai` | 3× model tiers of that provider. Anthropic: Claude Sonnet, Claude Haiku, Claude Sonnet (3rd slot duplicates the strongest available model with a distinct member name like `Claude-2`). Google: Gemini 2.5 Flash, Gemini 2.5 Flash-Lite, Gemini 2.5 Flash (duplicated). OpenAI: GPT-4o, GPT-4o-mini, GPT-4o (duplicated). Summary notes: "All three members use {provider} — add another key for cross-provider debate." |
| 6 | No cloud keys + Ollama reachable + ≥3 installed models that fit RAM | `local-safe` | 3× smallest installed Ollama models that fit |
| 7 | Ollama reachable but <3 installed models, OR all candidates exceed RAM | `mock-ollama-hint` | 3× mock; notice: `Install at least 3 local models, e.g. ollama pull llama3.2:3b` |
| 8 | Nothing detected | `mock` | 3× mock (current behaviour) |

### "Fits RAM" filter

Selected Ollama models pass the filter when:

```
sum(selected_model.size_bytes) ≤ 0.8 × total_ram_bytes
```

- The sum accounts for the parallel first-reading phase loading all local members concurrently.
- 0.8 leaves headroom for OS + Python.
- If `total_ram_bytes is None` (psutil unavailable), the filter is dropped — candidates are sorted by smallest `size_bytes` and the top N are selected unconditionally.

### Model version constants

`presets.py` declares model names as module-level constants at the top:

```python
CLAUDE_SONNET    = "claude-sonnet-4-6"
CLAUDE_HAIKU     = "claude-haiku-4-5-20251001"
GPT_4O           = "gpt-4o"
GPT_4O_MINI      = "gpt-4o-mini"
GEMINI_FLASH     = "gemini-2.5-flash"
GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"
```

Updating the default cloud models later = one edit per provider.

OpenAI defaults intentionally stay on `gpt-4o` / `gpt-4o-mini` for compatibility with the current Chat Completions provider implementation. Revisit these constants when the provider moves to the Responses API or explicitly supports GPT-5-family request parameters.

---

## Wizard confirmation UX (TTY path)

```
Welcome to Parliament. No config found — let's set one up.

Detected:
  ✓ ANTHROPIC_API_KEY (configured)
  ℹ OPENAI_API_KEY (not set)
  ℹ GOOGLE_API_KEY (not set)
  ✓ Ollama: reachable (5 models installed)
  System RAM: 32 GB

Proposed preset: mixed (1 cloud + 2 local)
  - Claude (anthropic / claude-sonnet-4-6)
  - Llama  (ollama / llama3.2:3b)
  - Gemma  (ollama / gemma2:2b)

Use these defaults? [Y/n]:
```

- `Y` (or empty enter): writes the proposed preset; prints `Wrote config to ~/.parliament/config.yaml`.
- `n` or any other input: writes the `mock` preset and prints `Wrote mock config to ~/.parliament/config.yaml — edit it via \`parliament\` (TUI member editor).`.
- EOF (`Ctrl-D`, closed stdin): same as `n`.

### Non-TTY path

Writes the detected preset silently, prints one line to stderr:

```
Created config at /home/user/.parliament/config.yaml (preset: mixed). Run `parliament doctor` for details.
```

### TTY detection

Both `sys.stdin.isatty()` and `sys.stdout.isatty()` must be True for the interactive path. If either is False (piped, redirected, scripted, inside a non-PTY container), the wizard takes the silent path.

---

## Doctor: Members viability check

New `_check_member_viability()`, called from `run_doctor()` between the providers section and `Next steps`. Renders under a new `[bold]Members[/bold]` heading.

### Per-member logic

- `provider == "mock"`: skip silently.
- `provider in {"anthropic","google","openai"}`:
    - If the corresponding `*_API_KEY` env var is unset → emit `!` warn: `Claude member needs ANTHROPIC_API_KEY`.
    - Else emit `✓`: `Claude (anthropic / claude-sonnet-4-6) — key configured`.
- `provider == "ollama"`:
    - Hit `/api/tags`. If `member.model` not present in the response → emit `!` warn with a `ollama pull` hint.
    - Else record `size_bytes` and emit `✓`: `Llama (ollama / llama3.2:3b) — installed, 2.0 GB`.

### Aggregate RAM check

After all members are inspected, sum recorded `size_bytes` for Ollama members. Let `total = sum`, `limit = 0.8 × system_ram_bytes`.

- `total > limit` → emit one `!` warn line:
  `Members may OOM: ~12.4 GB needed for local models, 16.0 GB RAM (limit 12.8 GB at 80%)`
- Else → emit one `✓` line:
  `Aggregate footprint: ~3.6 GB / 32.0 GB RAM (well within limit)`

If `psutil` is unavailable: emit one `ℹ` info line `RAM check skipped (psutil not installed)` and skip the aggregate test only — the per-model "not pulled" warnings still run.

### Exit code

All findings here are `warn`/`info` (never `ok=False`). The existing exit-code policy is unchanged: exit 1 only on hard environment failures (Python version, curses, etc.). Rationale: scripts that `parliament doctor && parliament ask "…"` shouldn't suddenly start exiting non-zero because of a stale model name; the warning is loud enough.

### Sample outputs

**Mixed preset, all good:**

```
Members
  ✓ Claude (anthropic / claude-sonnet-4-6) — key configured
  ✓ Llama (ollama / llama3.2:3b) — installed, 2.0 GB
  ✓ Gemma (ollama / gemma2:2b) — installed, 1.6 GB
  ✓ Aggregate footprint: ~3.6 GB / 32.0 GB RAM (well within limit)
```

**OOM risk:**

```
Members
  ✓ Claude (anthropic / claude-sonnet-4-6) — key configured
  ! Llama (ollama / deepseek-r1:8b) — installed, 5.2 GB
  ! Gemma (ollama / deepseek-r1:14b) — installed, 9.0 GB
  ! Members may OOM: ~14.2 GB needed for local models, 16.0 GB RAM (limit 12.8 GB at 80%)
```

**Stale model name in config:**

```
Members
  ✓ Claude (anthropic / claude-sonnet-4-6) — key configured
  ! Llama (ollama / llama3.2:3b) — not pulled. Run: ollama pull llama3.2:3b
  ✓ Gemma (ollama / gemma2:2b) — installed, 1.6 GB
```

---

## Error handling

| Scenario | Behaviour |
|---|---|
| Ollama probe timeout / connection refused | `ollama_reachable=False`, empty model list; preset rules 4/6/7 don't trigger. |
| `psutil` not importable | `total_ram_bytes=None`; RAM filter dropped during preset selection; doctor emits `ℹ RAM check skipped`. |
| Wizard write fails (disk full, permission denied) | Wizard raises; `_ensure_user_config()` catches the failure, falls back to `shutil.copyfile(EXAMPLE_CONFIG, USER_CONFIG)`, and prints a stderr warning. Existing safety net preserved. |
| EOF on stdin during the prompt | Treated as `n` → writes mock preset; no crash. |
| Two `parliament` invocations racing on first run | The `USER_CONFIG.exists()` check is the gate. The second invocation finds the config already written and skips the wizard. (No file lock — racing two `parliament` processes from a brand-new install is not a realistic flow.) |
| Config is malformed YAML on disk (post-wizard write) | Existing `yaml.safe_load` path handles this — unchanged. |

---

## Testing plan

New test files; each focused, each with deterministic fakes. No real network, no real Ollama, no real psutil.

### `tests/test_first_run_detect.py` — `detect_environment()`

- Env-var combinations → correct `Environment.keys` flags.
- Monkeypatched `httpx.get` returning `/api/tags` JSON with sizes → correct `ollama_models` list.
- `httpx.ConnectError` → `ollama_reachable=False`, empty model list.
- `psutil` monkeypatched to `None` → `total_ram_bytes=None`.

### `tests/test_first_run_presets.py` — `select_preset()`

- One parametrised test per row of the preset rules table (8 rows).
- Assert returned preset name + member provider/model list.
- Assert RAM filter excludes oversized Ollama models when RAM known.
- Assert <3 installed models routes to `mock-ollama-hint` rather than padding with duplicates.

### `tests/test_first_run_wizard.py` — `run_first_run_wizard()`

- TTY path with `y\n` → preset written, prompt printed.
- TTY path with `n` → mock preset written.
- TTY path with EOF → mock preset written, no crash.
- Non-TTY path → detected preset written silently, stderr notice printed.
- Wizard write failure → fallback to copying `EXAMPLE_CONFIG`, no exception escapes.
- End-to-end via `_ensure_user_config()` in a `tmp_path` HOME → file exists, loads cleanly via `load_config()`.

### `tests/test_doctor_member_viability.py` — new doctor check

- Cloud member, missing key → warn line.
- Ollama member not in `/api/tags` → warn line with `ollama pull` hint.
- Ollama members with sum > 80% RAM → aggregate OOM warn.
- Mock-only members → no Members section warnings.
- `psutil` missing → info line `RAM check skipped`; exit code still 0.

### `tests/test_model_catalog.py` — extend existing

- `fetch_ollama_models()` surfaces `size_bytes` per model.
- `PickerData.models` still returns the name list (backward-compat).

### `tests/conftest.py` additions

- `fake_ollama_tags(monkeypatch, models: list[tuple[str, int]])` helper wires up the `httpx.get` mock for `/api/tags` once and is reused across the new test files.

### Coverage target

Every branch in `select_preset()` exercised. The wizard prompt rendering is asserted by capturing the Rich `Console` output stream, not by golden-file matching (less brittle to formatting tweaks).

### Existing tests

No existing tests should change behaviour. The only edits to existing tests would be any that exercise `_ensure_user_config()` directly and expect `shutil.copyfile` — those switch to asserting on the new wizard entry point. Current count is ~321; this design adds 30–40 new tests.

---

## Build sequence (sketch — full plan to be written next via `writing-plans`)

1. Extend `fetch_ollama_models()` to return sizes (smallest change, unblocks downstream code).
2. Add `presets.py` with `Preset` dataclass + `select_preset()` + one builder per preset (pure functions, fully testable on their own).
3. Add `first_run.py` with `detect_environment()` and `run_first_run_wizard()`.
4. Wire `_ensure_user_config()` → `run_first_run_wizard()` with fallback.
5. Add `psutil` to `pyproject.toml`.
6. Add `_check_member_viability()` to `doctor.py`.
7. Test pass — ruff + pytest clean.
