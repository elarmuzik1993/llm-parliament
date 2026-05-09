"""Markdown rendering — Obsidian/GitHub callouts, level-gated sections."""

from __future__ import annotations

from parliament.render.hansard import HansardLevel, render_markdown


# --- Task 5: minimal level ---

def test_minimal_renders_question_h1_and_recommendation_callout(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "# Should we use Postgres or MongoDB?" in md
    assert "> [!success] Recommendation" in md
    assert "Postgres. ACID + JSON columns" in md


def test_minimal_omits_consensus_split_risks(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "[!info] Consensus" not in md
    assert "[!warning] Split" not in md
    assert "[!danger] Risks" not in md


def test_minimal_omits_frontmatter_and_footer(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "---" not in md.split("\n", 5)[0]  # no YAML opener as first line
    assert "## Session" not in md
    assert "id:" not in md.split("# ", 1)[0]  # no frontmatter before H1


def test_minimal_omits_transcripts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.MINIMAL)
    assert "## First Reading" not in md
    assert "## Debate" not in md


# --- Task 6: verdict callouts in correct order ---

def test_verdict_renders_all_four_callouts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.VERDICT)
    assert "> [!info] Consensus" in md
    assert "> [!warning] Split" in md
    assert "> [!danger] Risks" in md
    assert "> [!success] Recommendation" in md


def test_verdict_callouts_appear_in_canonical_order(make_hansard):
    """Consensus → Split → Risks → Recommendation. Recommendation last."""
    md = render_markdown(make_hansard(), HansardLevel.VERDICT)
    positions = {
        "consensus":      md.index("> [!info] Consensus"),
        "split":          md.index("> [!warning] Split"),
        "risks":          md.index("> [!danger] Risks"),
        "recommendation": md.index("> [!success] Recommendation"),
    }
    assert positions["consensus"] < positions["split"]
    assert positions["split"] < positions["risks"]
    assert positions["risks"] < positions["recommendation"]


def test_verdict_callout_body_is_blockquoted(make_hansard):
    md = render_markdown(make_hansard(consensus="One.\nTwo."), HansardLevel.VERDICT)
    # Each line of body must be `> ` prefixed.
    assert "> One." in md
    assert "> Two." in md


def test_callout_bullet_list_lines_are_blockquoted(make_hansard):
    md = render_markdown(
        make_hansard(risks="- First risk\n- Second risk"),
        HansardLevel.VERDICT,
    )
    assert "> - First risk" in md
    assert "> - Second risk" in md


# --- Task 7: empty section omission + recommendation fallback ---

def test_empty_split_section_is_omitted(make_hansard):
    md = render_markdown(make_hansard(split=""), HansardLevel.VERDICT)
    assert "[!warning] Split" not in md
    # Other sections still present
    assert "[!info] Consensus" in md
    assert "[!success] Recommendation" in md


def test_empty_consensus_and_risks_omitted(make_hansard):
    md = render_markdown(make_hansard(consensus="", risks=""), HansardLevel.VERDICT)
    assert "[!info] Consensus" not in md
    assert "[!danger] Risks" not in md
    assert "[!success] Recommendation" in md  # still present


def test_empty_recommendation_renders_placeholder(make_hansard):
    md = render_markdown(make_hansard(recommendation=""), HansardLevel.VERDICT)
    assert "> [!success] Recommendation" in md
    assert "(no recommendation parsed)" in md


def test_whitespace_only_section_treated_as_empty(make_hansard):
    md = render_markdown(make_hansard(split="   \n  \n"), HansardLevel.VERDICT)
    assert "[!warning] Split" not in md


# --- Task 8: archive level (frontmatter + footer) ---

def test_archive_includes_yaml_frontmatter(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    lines = md.split("\n")
    assert lines[0] == "---"
    assert any(line.startswith("id: ") for line in lines[:10])
    assert any(line.startswith("created_at: ") for line in lines[:10])
    assert "type: parliament-hansard" in md
    assert any(line.startswith("speaker: ") for line in lines[:10])
    assert "members:" in md


def test_archive_frontmatter_lists_each_member(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    # Each of the three default members should appear under `members:`
    assert "Alpha (mock/mock-v1)" in md
    assert "Beta (mock/mock-v2)" in md
    assert "Gamma (mock/mock-v3)" in md


def test_archive_includes_session_footer(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    assert "## Session" in md
    assert "- Speaker: Alpha" in md
    assert "- Calls: 7" in md  # 3 members * 2 phases + 1 division
    assert "- Duration: 12.3s" in md  # from default duration_ms=12345


def test_archive_still_omits_transcripts(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.ARCHIVE)
    assert "## First Reading" not in md
    assert "## Debate" not in md


# --- Task 9: full level (transcripts) ---

def test_full_includes_first_reading_section(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert "## First Reading" in md
    # Each member's heading + content
    assert "### Alpha" in md
    assert "First-reading content body. (Alpha)" in md
    assert "First-reading content body. (Beta)" in md
    assert "First-reading content body. (Gamma)" in md


def test_full_includes_debate_section(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert "## Debate" in md
    assert "### Alpha (critique)" in md
    assert "Debate critique content body. (Alpha)" in md


def test_full_includes_frontmatter_and_footer(make_hansard):
    """Full is a strict superset of archive."""
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    assert md.startswith("---\n")
    assert "## Session" in md


def test_full_transcripts_appear_after_verdict(make_hansard):
    md = render_markdown(make_hansard(), HansardLevel.FULL)
    rec_idx = md.index("> [!success] Recommendation")
    fr_idx = md.index("## First Reading")
    debate_idx = md.index("## Debate")
    assert rec_idx < fr_idx
    assert fr_idx < debate_idx
