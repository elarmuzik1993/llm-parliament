"""The Speaker says whether the debate is still contested, and on what (#9).

An agent calling the parliament needs a decidable flag, not prose. The Speaker
ends its synthesis with two labelled lines; a missing or unclear answer is
None (unknown), never False.
"""

import json

import pytest

from parliament.core.parliament import Parliament
from parliament.core.types import Bill, Hansard, Member, Synthesis
from parliament.procedures.division import PROMPT_TEMPLATE, parse_synthesis
from parliament.providers.mock import MockProvider

BODY = (
    "CONSENSUS:\nAll reject B.\n\n"
    "SPLIT:\nTwo choose A, one chooses C.\n\n"
    "RISKS:\n- Schedule slip\n\n"
    "RECOMMENDATION:\nChoose A."
)


def test_prompt_asks_for_both_lines():
    assert "CONTESTED:" in PROMPT_TEMPLATE
    assert "ON WHAT:" in PROMPT_TEMPLATE


def test_contested_yes_records_what_they_disagree_on():
    s = parse_synthesis(BODY + "\n\nCONTESTED: yes\nON WHAT: Rust rewrite or sandbox.", "S")
    assert s.contested is True
    assert s.contested_on == "Rust rewrite or sandbox."


def test_trailer_is_kept_out_of_the_recommendation():
    raw = BODY + "\n\nCONTESTED: yes\nON WHAT: Rust rewrite or sandbox."
    s = parse_synthesis(raw, "S")
    assert s.recommendation == "Choose A."
    assert s.raw == raw


def test_contested_no_has_nothing_to_be_contested_on():
    s = parse_synthesis(BODY + "\n\nCONTESTED: no\nON WHAT: none", "S")
    assert s.contested is False
    assert s.contested_on == ""


@pytest.mark.parametrize(
    "trailer",
    [
        "**CONTESTED:** Yes\n**ON WHAT:** Rust rewrite or sandbox.",
        "- Contested: yes\n- On what: Rust rewrite or sandbox.",
        "CONTESTED: yes\nON WHAT:\nRust rewrite or sandbox.",
    ],
)
def test_markdown_and_layout_around_the_labels_is_tolerated(trailer):
    s = parse_synthesis(BODY + "\n\n" + trailer, "S")
    assert s.contested is True
    assert s.contested_on == "Rust rewrite or sandbox."
    assert s.recommendation == "Choose A."


@pytest.mark.parametrize("answer", ["partly", "", "maybe yes"])
def test_unclear_answer_is_unknown_not_false(answer):
    s = parse_synthesis(BODY + f"\n\nCONTESTED: {answer}\nON WHAT: scope", "S")
    assert s.contested is None
    assert s.contested_on == ""


def test_missing_trailer_is_unknown_and_changes_nothing_else():
    s = parse_synthesis(BODY, "S")
    assert s.contested is None
    assert s.contested_on == ""
    assert s.recommendation == "Choose A."


def test_a_label_quoted_early_is_not_the_speakers_answer():
    raw = BODY.replace(
        "Two choose A", "One member wrote 'CONTESTED: yes' in its notes. Two choose A"
    ) + "\n\nThe members' reasoning differs in emphasis.\nMore detail.\nAnd more.\n" \
        "Still more.\nFinal line.\nLast line."
    assert parse_synthesis(raw, "S").contested is None


def test_trailer_without_section_headers_still_parses():
    s = parse_synthesis("Just choose A.\n\nCONTESTED: no\nON WHAT: none", "S")
    assert s.contested is False
    assert s.recommendation == "Just choose A."


async def test_mock_debate_records_contested():
    members = [Member(name=n, provider_name="mock", model=f"mock-{n}") for n in "AB"]
    providers = {m.name: MockProvider(model=m.model, latency_ms=0) for m in members}
    hansard = await Parliament(members, providers).ask("Postgres or Mongo?")
    assert hansard.synthesis.contested is False
    assert hansard.synthesis.contested_on == ""


def test_contested_round_trip_and_old_records_load():
    synthesis = Synthesis(speaker_name="A", contested=True, contested_on="scope")
    hansard = Hansard(Bill(content="q"), [], [], [], synthesis)
    data = json.loads(hansard.to_json())
    assert data["synthesis"]["contested"] is True
    assert data["synthesis"]["contested_on"] == "scope"
    assert Hansard.from_dict(data) == hansard
    del data["synthesis"]["contested"], data["synthesis"]["contested_on"]
    old = Hansard.from_dict(data).synthesis
    assert (old.contested, old.contested_on) == (None, "")
