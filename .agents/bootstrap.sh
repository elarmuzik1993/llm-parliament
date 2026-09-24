#!/usr/bin/env bash
# Install the dev dependencies scripts/verify.sh needs. Cloud agent sessions start from a fresh
# clone, so the session-start hook runs this there; locally it is a no-op once installed.

set -eu
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=""
for p in python python3; do "$p" -c '' >/dev/null 2>&1 && { PY=$p; break; }; done
[ -n "$PY" ] || { echo "bootstrap: no working python on PATH" >&2; exit 1; }

"$PY" -c "import mypy, pytest, ruff" >/dev/null 2>&1 && exit 0
"$PY" -m pip install -q -e ".[dev]"
