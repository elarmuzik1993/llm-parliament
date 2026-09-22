"""`docs/configuration.md` must agree with the code it documents.

The reference doc repeats three facts the code already holds: which
`provider:` values exist, which of them take a `providers.<name>` block, and
which environment variables carry a key. Nothing failed when those copies
drifted apart, so they did -- #49 and #57 exist only to correct documentation
the code had outgrown, and the provider list went stale again the next time a
vendor was wired.

These tests are the guard named in AGENTS.md under **Scope & invariants**:
they fail when a copy disagrees with its source, which is the only thing that
makes a copy safe to keep.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _repo_root() -> Path | None:
    """Repo root, or None when running against an installed (non-editable) copy."""
    root = Path(__file__).resolve().parent.parent
    return root if (root / "config.example.yaml").is_file() else None


def _reference() -> str:
    root = _repo_root()
    if root is None:
        pytest.skip("not running from a source checkout")
    return (root / "docs" / "configuration.md").read_text(encoding="utf-8")


def _first_column(markdown: str, header: str) -> set[str]:
    """Backticked values in column one of the table under `header`.

    Stops at the next heading, so a table is read from its own section only.
    """
    section = markdown.split(f"\n## {header}\n", 1)
    assert len(section) == 2, f"no '## {header}' section in docs/configuration.md"
    body = re.split(r"\n## ", section[1], maxsplit=1)[0]
    values: set[str] = set()
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cell = line.split("|")[1].strip()
        match = re.fullmatch(r"`([^`]+)`", cell)
        if match:
            values.add(match.group(1))
    return values


def _known_providers() -> set[str]:
    """Every name `create_provider` accepts, derived from its own tables.

    Derived rather than listed: a literal here would be one more copy to
    drift. Stage 1 of the plan on #15 replaces these three tables with one
    registry, and this helper becomes a read of it.
    """
    from parliament.providers import _CLOUD_PROVIDERS, _OPENAI_COMPATIBLE_PROVIDERS

    return {"mock", "ollama"} | set(_CLOUD_PROVIDERS) | set(_OPENAI_COMPATIBLE_PROVIDERS)


def test_every_key_variable_is_documented() -> None:
    """A key variable the docs omit is one nobody knows to set."""
    from parliament.config import KEY_PROVIDERS

    documented = _first_column(_reference(), "Environment variables")
    missing = set(KEY_PROVIDERS.values()) - documented
    assert not missing, (
        f"{sorted(missing)} in KEY_PROVIDERS but absent from the environment-variable "
        "table in docs/configuration.md"
    )


def test_the_providers_table_lists_every_provider() -> None:
    """`providers.<name>` is per provider, so every provider needs a row."""
    documented = _first_column(_reference(), "`providers`")
    assert documented == _known_providers(), (
        "the providers table in docs/configuration.md disagrees with the names "
        f"create_provider accepts: documented={sorted(documented)}, "
        f"accepted={sorted(_known_providers())}"
    )


def test_the_documented_provider_values_are_the_accepted_ones() -> None:
    """The `provider:` row promises a closed set -- it must be the real one."""
    row = re.search(
        r"\|\s*`parliament\.members\[\]\.provider`\s*\|[^|]*\|[^|]*\|([^|]*)\|",
        _reference(),
    )
    assert row, "no `parliament.members[].provider` row in docs/configuration.md"
    listed = set(re.findall(r"`([^`]+)`", row.group(1)))
    assert listed == _known_providers(), (
        "the documented `provider:` values are not the ones create_provider accepts: "
        f"documented={sorted(listed)}, accepted={sorted(_known_providers())}"
    )
