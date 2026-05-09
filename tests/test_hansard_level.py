"""HansardLevel enum, parse, and section-inclusion matrix."""
from __future__ import annotations

import warnings

import pytest

from parliament.render.hansard import HansardLevel


def test_levels_exist():
    assert HansardLevel.MINIMAL.value == "minimal"
    assert HansardLevel.VERDICT.value == "verdict"
    assert HansardLevel.ARCHIVE.value == "archive"
    assert HansardLevel.FULL.value == "full"


def test_levels_are_string_enums():
    """HansardLevel inherits from str so YAML serialization is trivial."""
    assert isinstance(HansardLevel.VERDICT, str)
    assert HansardLevel.VERDICT == "verdict"


@pytest.mark.parametrize("raw,expected", [
    ("minimal", HansardLevel.MINIMAL),
    ("verdict", HansardLevel.VERDICT),
    ("archive", HansardLevel.ARCHIVE),
    ("full", HansardLevel.FULL),
    ("VERDICT", HansardLevel.VERDICT),
    ("  full  ", HansardLevel.FULL),
])
def test_parse_known_values(raw, expected):
    assert HansardLevel.parse(raw) is expected


def test_parse_none_returns_verdict_default():
    assert HansardLevel.parse(None) is HansardLevel.VERDICT


def test_parse_unknown_returns_verdict_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = HansardLevel.parse("nonsense")
    assert result is HansardLevel.VERDICT
    assert any("nonsense" in str(w.message) for w in caught)


def test_parse_empty_string_returns_verdict():
    assert HansardLevel.parse("") is HansardLevel.VERDICT
