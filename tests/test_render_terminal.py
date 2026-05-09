"""Terminal rendering — Rich panels mirroring the markdown callouts."""

from __future__ import annotations

import io

from rich.console import Console

from parliament.render.hansard import HansardLevel, render_terminal


def _capture(level, hansard) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    render_terminal(hansard, level, console)
    return buf.getvalue()


# --- Task 10: minimal + verdict levels ---

def test_minimal_renders_question_panel_and_recommendation_only(make_hansard):
    out = _capture(HansardLevel.MINIMAL, make_hansard())
    assert "Should we use Postgres or MongoDB?" in out
    assert "✓ Recommendation" in out
    assert "Postgres. ACID" in out
    # No other verdict panels at minimal
    assert "ℹ Consensus" not in out
    assert "⚖ Split" not in out
    assert "! Risks" not in out


def test_verdict_renders_all_four_panels(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "ℹ Consensus" in out
    assert "⚖ Split" in out
    assert "! Risks" in out
    assert "✓ Recommendation" in out


def test_verdict_panels_in_canonical_order(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert out.index("ℹ Consensus") < out.index("⚖ Split")
    assert out.index("⚖ Split") < out.index("! Risks")
    assert out.index("! Risks") < out.index("✓ Recommendation")


def test_verdict_omits_transcripts_in_terminal(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "📖 First Reading" not in out
    assert "🗣 Debate" not in out


def test_empty_section_panel_omitted(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard(split=""))
    assert "⚖ Split" not in out


def test_empty_recommendation_renders_placeholder(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard(recommendation=""))
    assert "✓ Recommendation" in out
    assert "(no recommendation parsed)" in out


# --- Task 11: full level (transcripts) + archive footer ---

def test_full_renders_first_reading_panels(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert "📖 First Reading" in out
    # Each member's first-reading content
    assert "First-reading content body. (Alpha)" in out
    assert "First-reading content body. (Beta)" in out
    assert "First-reading content body. (Gamma)" in out


def test_full_renders_debate_panels(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert "🗣 Debate" in out
    assert "Alpha (critique)" in out
    assert "Debate critique content body. (Alpha)" in out


def test_full_transcripts_appear_after_verdict(make_hansard):
    out = _capture(HansardLevel.FULL, make_hansard())
    assert out.index("✓ Recommendation") < out.index("📖 First Reading")
    assert out.index("📖 First Reading") < out.index("🗣 Debate")


def test_archive_renders_session_footer_in_terminal(make_hansard):
    out = _capture(HansardLevel.ARCHIVE, make_hansard())
    assert "Session: 12.3s" in out
    assert "Calls: 7" in out
    assert "Speaker: Alpha" in out


def test_verdict_does_not_render_session_footer(make_hansard):
    out = _capture(HansardLevel.VERDICT, make_hansard())
    assert "Session:" not in out
    assert "Calls:" not in out
