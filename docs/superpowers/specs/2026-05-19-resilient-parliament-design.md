# Resilient Parliament — Drop-and-Continue Design

**Date:** 2026-05-19
**Status:** Approved
**Linear:** USE-35 (to be created)

## Problem

When one provider fails during a parliamentary session, the whole run aborts and the user gets no output — even though the other providers finished successfully and produced good work. Additionally, if a provider is selected as Division Speaker but had already failed in First Reading, Division also fails, wasting another API call.

## Goal

Always produce a Hansard. If any provider fails at any phase, drop it and continue with the survivors. Never call a failed provider again in subsequent phases.

## Behavior

### Any provider failure → drop and continue

The same rule applies to every provider (Claude, GPT-4o, Gemini, any Ollama model) and every error type (429 quota, 401 auth, 404 model-not-found, timeout, 5xx, OOM, connection refused):

1. Provider fails → dropped from the session with a progress warning
2. Remaining providers continue normally
3. If ≥2 providers survive → full Debate + Division → valid Hansard
4. If <2 providers survive → clear error: "Not enough members responded to continue"

### Fatal vs transient distinction: messaging only

`is_fatal_provider_error()` is kept but used only to produce a richer warning message in the progress stream:

- Fatal (429 quota, 401/403 auth, 404 model-not-found): `"Gemini quota exceeded — check billing. Continuing with 2 members."`
- Transient (timeout, 5xx, connection): `"Gemini timed out. Continuing with 2 members."`

The behavior (drop) is identical in both cases.

### Phases

```
First Reading (all providers in parallel):
  Provider A  → success → included in Debate
  Provider B  → ❌ any error → dropped, warning shown
  Provider C  → success → included in Debate

Debate (only A + C):
  A and C critique each other — B never called

Division (Speaker from A or C only):
  A or C synthesises — B never considered for Speaker
  → Hansard produced ✓
```

## Changes Required

### 1. `src/parliament/procedures/first_reading.py`

Remove the abort-on-fatal block added in the previous session. Restore pure drop-and-continue for all errors.

No change to progress event error strings — `format_provider_error()` already produces distinct, actionable messages for fatal vs transient errors (e.g. "quota exceeded — check billing" vs "timed out").

### 2. `src/parliament/procedures/debate.py`

Same as above — remove abort-on-fatal block. The existing `active_members` filter already correctly excludes First Reading failures from Debate; no other change needed there.

### 3. `src/parliament/core/parliament.py` — `ask()`

Fix the Division Speaker selection bug. Currently `select_speaker` receives `self.members` (all configured members, including failed ones). Change it to receive only surviving members — those present in the `debate` response list:

```python
surviving_members = [m for m in self.members if any(r.member_name == m.name for r in debate)]
speaker, speaker_provider = select_speaker(
    members=surviving_members,
    providers=self.providers,
    ...
)
```

### 4. `src/parliament/providers/errors.py`

No functional change. `is_fatal_provider_error()` is already correct and stays for messaging purposes.

## What Does NOT Change

- Minimum viable threshold: ≥2 survivors required throughout (First Reading and Debate both enforce this)
- Parallel execution in First Reading and Debate — no sequential fallback
- All existing tests for transient-error drop-and-continue continue to pass
- `is_fatal_provider_error()` and its tests are kept

## Tests

### Modify
- `tests/test_fatal_provider_errors.py` — change `test_first_reading_aborts_on_fatal_error` and `test_debate_aborts_on_fatal_error` to assert the run continues (not aborts) and produces 2-member output

### Add
- `test_division_speaker_not_selected_from_failed_member` — First Reading: 2 succeed (tier 3) + 1 fails (tier 1, would normally be Speaker). Assert Division uses one of the 2 survivors, not the failed tier-1 member.
- `test_full_pipeline_one_fatal_one_transient_survivor` — 1 fatal error + 1 transient error from different members → only 1 survivor → assert RuntimeError "not enough members"

## Rollback

The abort-on-fatal feature (introduced in the previous session) was never released — it exists only on the local `main` branch. Reverting it is safe.
