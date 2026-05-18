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


from parliament.render.hansard import includes  # noqa: E402


def test_minimal_includes_only_question_and_recommendation():
    assert includes(HansardLevel.MINIMAL, "question")
    assert includes(HansardLevel.MINIMAL, "recommendation")
    assert not includes(HansardLevel.MINIMAL, "consensus")
    assert not includes(HansardLevel.MINIMAL, "split")
    assert not includes(HansardLevel.MINIMAL, "risks")
    assert not includes(HansardLevel.MINIMAL, "frontmatter")


def test_verdict_includes_full_synthesis_block():
    for section in ("question", "consensus", "split", "risks", "recommendation"):
        assert includes(HansardLevel.VERDICT, section), section
    assert not includes(HansardLevel.VERDICT, "frontmatter")
    assert not includes(HansardLevel.VERDICT, "footer")
    assert not includes(HansardLevel.VERDICT, "first_reading")


def test_archive_adds_frontmatter_and_footer_only():
    assert includes(HansardLevel.ARCHIVE, "frontmatter")
    assert includes(HansardLevel.ARCHIVE, "footer")
    assert not includes(HansardLevel.ARCHIVE, "first_reading")
    assert not includes(HansardLevel.ARCHIVE, "debate")


def test_full_includes_everything():
    for section in (
        "frontmatter", "question", "consensus", "split", "risks",
        "recommendation", "footer", "first_reading", "debate",
    ):
        assert includes(HansardLevel.FULL, section), section


def test_levels_are_monotonic():
    """Each level's section set must be a superset of the level below."""
    from parliament.render.hansard import _LEVEL_SECTIONS
    levels = [HansardLevel.MINIMAL, HansardLevel.VERDICT, HansardLevel.ARCHIVE, HansardLevel.FULL]
    for lower, higher in zip(levels, levels[1:]):
        assert _LEVEL_SECTIONS[lower] <= _LEVEL_SECTIONS[higher], (
            f"{higher.value} must include all sections of {lower.value}"
        )


def test_unknown_section_returns_false():
    assert not includes(HansardLevel.FULL, "nonsense_section")
