"""Links in the README and the usage guide must lead somewhere.

The README is also the PyPI page, where relative links break, so it links into
the repo by absolute `blob/main` URLs. Nothing fails when a file is renamed or
a heading reworded under such a link; this test does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_URL = "https://github.com/elarmuzik1993/llm-parliament/blob/main/"
DOCS = ["README.md", "docs/usage.md"]

_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _repo_root() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    return root if (root / "pyproject.toml").exists() else None


def _anchors(markdown: str) -> set[str]:
    """GitHub's heading slugs, ignoring `#` lines inside code fences."""
    anchors: set[str] = set()
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        match = None if in_fence else re.match(r"^#{1,6} (.+)$", line)
        if match:
            slug = re.sub(r"[^\w\- ]", "", match.group(1).strip().lower())
            anchors.add(slug.replace(" ", "-"))
    return anchors


def _targets(root: Path, doc: str) -> list[tuple[str, Path, str]]:
    """(link, file it points to, anchor or "") for every link into the repo."""
    source = root / doc
    found = []
    for link in _LINK.findall(source.read_text(encoding="utf-8")):
        if link.startswith(REPO_URL):
            path, _, anchor = link[len(REPO_URL):].partition("#")
            target = root / path
        elif link.startswith(("http://", "https://", "mailto:")):
            continue
        else:
            path, _, anchor = link.partition("#")
            target = (source.parent / path) if path else source
        found.append((link, target, anchor))
    return found


@pytest.mark.parametrize("doc", DOCS)
def test_every_link_into_the_repo_resolves(doc):
    root = _repo_root()
    if root is None:
        pytest.skip("not running from a source checkout")
    broken = []
    for link, target, anchor in _targets(root, doc):
        if not target.exists():
            broken.append(f"{link}: no such file")
        elif (
            anchor
            and target.suffix == ".md"
            and anchor not in _anchors(target.read_text(encoding="utf-8"))
        ):
            broken.append(f"{link}: no heading #{anchor}")
    assert broken == []


def test_the_readme_has_no_relative_links():
    """Relative links break on PyPI, which renders the README as the project page."""
    root = _repo_root()
    if root is None:
        pytest.skip("not running from a source checkout")
    text = (root / "README.md").read_text(encoding="utf-8")
    relative = [
        link for link in _LINK.findall(text)
        if not link.startswith(("http://", "https://", "#", "mailto:"))
    ]
    assert relative == []
