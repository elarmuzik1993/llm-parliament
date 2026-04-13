"""Test synthesis section parser — well-formed, malformed, and garbage input."""

from parliament.procedures.division import parse_synthesis


def test_well_formatted():
    raw = (
        "CONSENSUS:\nAll agree on X.\n\n"
        "SPLIT:\nA disagrees with B on Y.\n\n"
        "RISKS:\n- Risk 1\n- Risk 2\n\n"
        "RECOMMENDATION:\nDo X with caution."
    )
    s = parse_synthesis(raw, "Speaker")
    assert s.speaker_name == "Speaker"
    assert "All agree" in s.consensus
    assert "disagrees" in s.split
    assert "Risk 1" in s.risks
    assert "Do X" in s.recommendation
    assert s.raw == raw


def test_missing_sections():
    """Some sections present, others missing — present ones filled, missing ones empty."""
    raw = "CONSENSUS:\nWe agree.\n\nRECOMMENDATION:\nGo for it."
    s = parse_synthesis(raw, "Speaker")
    assert "We agree" in s.consensus
    assert "Go for it" in s.recommendation
    assert s.split == ""
    assert s.risks == ""


def test_garbage_no_sections():
    """No recognizable sections — entire response into recommendation."""
    raw = "This is just a freeform response with no structure at all."
    s = parse_synthesis(raw, "Speaker")
    assert s.consensus == ""
    assert s.split == ""
    assert s.risks == ""
    assert s.recommendation == raw.strip()


def test_extra_text_around_sections():
    """Preamble and trailing text shouldn't break parsing."""
    raw = (
        "Here is my synthesis of the debate:\n\n"
        "CONSENSUS:\nEveryone agrees.\n\n"
        "SPLIT:\nSome disagree.\n\n"
        "RISKS:\nWatch out.\n\n"
        "RECOMMENDATION:\nProceed.\n\n"
        "Thank you for the debate."
    )
    s = parse_synthesis(raw, "Speaker")
    assert "Everyone agrees" in s.consensus
    assert "Some disagree" in s.split
    assert "Watch out" in s.risks
    # Recommendation may include trailing text — that's fine
    assert "Proceed" in s.recommendation


def test_reordered_sections():
    """Sections in non-standard order should still parse."""
    raw = (
        "RECOMMENDATION:\nDo this.\n\n"
        "RISKS:\nBe careful.\n\n"
        "CONSENSUS:\nAll agree.\n\n"
        "SPLIT:\nNone."
    )
    s = parse_synthesis(raw, "Speaker")
    assert "Do this" in s.recommendation
    assert "Be careful" in s.risks
    assert "All agree" in s.consensus
    assert "None" in s.split


def test_sections_without_colons():
    """Headers like 'CONSENSUS' without colon should still work."""
    raw = "CONSENSUS\nAgreed.\n\nSPLIT\nDisagreed.\n\nRISKS\nRisky.\n\nRECOMMENDATION\nDo it."
    s = parse_synthesis(raw, "Speaker")
    assert "Agreed" in s.consensus
    assert "Do it" in s.recommendation
