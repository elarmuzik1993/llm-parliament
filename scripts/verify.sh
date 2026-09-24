#!/usr/bin/env bash
# The one verification command: exactly what CI runs (.github/workflows/ci.yml), in one go.
#
#   bash scripts/verify.sh           ruff, mypy, pytest
#   bash scripts/verify.sh --quick   ruff alone; silent when clean (agent session start)
#
# CHECKS is a copy of ci.yml's run steps. tests/test_verify_matches_ci.py fails when the two
# disagree, which is what makes the copy safe to keep (AGENTS.md, Scope & invariants).
# Needs the dev dependencies: python -m pip install -e ".[dev]"

set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

CHECKS=(
    "ruff check ."
    "mypy src/parliament"
    "python -m pytest -q"
)

quick=0
case "${1:-}" in
    --quick) quick=1 ;;
    "") ;;
    *) echo "usage: bash scripts/verify.sh [--quick]" >&2; exit 2 ;;
esac

# `python` in a venv and on Windows, `python3` elsewhere. The Windows Store stub fails even -c ''.
PY=""
for p in python python3; do "$p" -c '' >/dev/null 2>&1 && { PY=$p; break; }; done
[ -n "$PY" ] || { echo "verify: no working python on PATH" >&2; exit 2; }
if ! "$PY" -c "import mypy, pytest, ruff" >/dev/null 2>&1; then
    echo "verify: dev dependencies missing; run: $PY -m pip install -e \".[dev]\"" >&2
    exit 1
fi

failed=0
for check in "${CHECKS[@]}"; do
    [ "$quick" = 1 ] && [ "${check%% *}" != ruff ] && continue
    read -r -a argv <<< "$check"
    # Every tool runs as a module of the same interpreter, so an unactivated venv still works.
    if [ "${argv[0]}" = python ]; then argv=("$PY" "${argv[@]:1}"); else argv=("$PY" -m "${argv[@]}"); fi
    if out=$("${argv[@]}" 2>&1); then
        [ "$quick" = 1 ] || printf 'ok    %s\n' "$check"
    else
        failed=1
        printf 'FAIL  %s\n%s\n' "$check" "$(printf '%s\n' "$out" | tail -n 30)"
    fi
done

[ "$failed" = 0 ] || exit 1
[ "$quick" = 1 ] || printf '\nverify: all checks passed\n'
exit 0
