"""`scripts/verify.sh` must run exactly what CI runs.

verify.sh copies the check commands out of `.github/workflows/ci.yml`, so that one local command
means the same as a green PR. A copy that can drift without anything failing is the failure
AGENTS.md describes under **Scope & invariants**; this test is the guard that makes it safe to keep.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _repo_root() -> Path | None:
    """Repo root, or None when running against an installed (non-editable) copy."""
    root = Path(__file__).resolve().parent.parent
    return root if (root / ".github" / "workflows" / "ci.yml").is_file() else None


def _ci_checks(root: Path) -> set[str]:
    """Every `run:` step in ci.yml except the dependency install."""
    text = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    runs = re.findall(r"^\s*run:\s*(\S.*?)\s*$", text, re.MULTILINE)
    return {run for run in runs if "pip install" not in run}


def _verify_checks(root: Path) -> set[str]:
    """The quoted commands in verify.sh's CHECKS=( ... ) block."""
    text = (root / "scripts" / "verify.sh").read_text(encoding="utf-8")
    block = re.search(r"^CHECKS=\(\n(.*?)^\)", text, re.MULTILINE | re.DOTALL)
    assert block, "scripts/verify.sh has no CHECKS=( ... ) block"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def test_verify_runs_exactly_the_ci_checks() -> None:
    root = _repo_root()
    if root is None:
        pytest.skip("not running from a source checkout")
    ci = _ci_checks(root)
    assert ci, "found no run steps in ci.yml; has its layout changed?"
    assert _verify_checks(root) == ci
