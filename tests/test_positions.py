"""Self-reported member positions (#69): parsing, phases, and Hansard round-trip."""

import json

import pytest

from parliament.core.parliament import Parliament
from parliament.core.types import Bill, Hansard, Member, Position, Response, Synthesis
from parliament.procedures.positions import parse_position
from parliament.providers.mock import MockProvider


def test_debate_trailer_parses_stance_and_changed_mind():
    content = "Long critique...\n\nPOSITION: Use Postgres.\nCHANGED MIND: yes"
    assert parse_position(content) == Position(stance="Use Postgres.", changed_mind=True)


def test_first_reading_trailer_has_no_changed_mind():
    assert parse_position("Analysis.\nPOSITION: Use Postgres.") == Position("Use Postgres.")


@pytest.mark.parametrize(
    "content",
    [
        "**POSITION:** Use Postgres.\n**CHANGED MIND:** No",
        "- Position: Use Postgres.\n- Changed mind: no.",
        "### POSITION: Use Postgres.\nCHANGED_MIND: NO",
    ],
)
def test_markdown_around_the_labels_is_tolerated(content):
    assert parse_position(content) == Position(stance="Use Postgres.", changed_mind=False)


@pytest.mark.parametrize(
    "content",
    [
        "**POSITION:**\nUse Postgres.\n\n**CHANGED MIND:**\nNo",
        "POSITION:\n\nUse Postgres.\nCHANGED MIND:\n**no**",
    ],
)
def test_answer_on_the_line_after_its_label(content):
    assert parse_position(content) == Position(stance="Use Postgres.", changed_mind=False)


def test_both_answers_on_one_line_are_split():
    content = "POSITION: Use Postgres. **CHANGED MIND:** yes"
    assert parse_position(content) == Position(stance="Use Postgres.", changed_mind=True)


def test_empty_label_does_not_borrow_the_changed_mind_line():
    assert parse_position("POSITION:\nCHANGED MIND: no") is None


def test_windows_line_endings_leave_no_carriage_return():
    content = "Analysis.\r\nPOSITION: Use Postgres.\r\nCHANGED MIND: no\r\n"
    assert parse_position(content) == Position(stance="Use Postgres.", changed_mind=False)


def test_peer_position_quoted_early_is_not_the_members_own():
    # Debate prompts carry the peers' First Readings, trailers included.
    content = (
        "Member B said:\nPOSITION: Use Mongo.\n\n"
        + "\n".join(f"Point {i} of my critique." for i in range(8))
    )
    assert parse_position(content) is None


def test_first_reading_ignores_a_volunteered_changed_mind():
    content = "POSITION: Use Postgres.\nCHANGED MIND: no"
    position = parse_position(content, with_changed_mind=False)
    assert position == Position(stance="Use Postgres.", changed_mind=None)


def test_last_position_line_wins_over_earlier_prose():
    content = "Position: the old one.\n\nRevised.\nPOSITION: the new one."
    assert parse_position(content).stance == "the new one."


@pytest.mark.parametrize("content", ["", "No trailer at all.", "POSITION:", "POSITION: **"])
def test_missing_or_empty_position_is_none(content):
    assert parse_position(content) is None


def test_unclear_changed_mind_is_none_not_false():
    position = parse_position("POSITION: Use Postgres.\nCHANGED MIND: partly")
    assert position == Position(stance="Use Postgres.", changed_mind=None)


async def test_mock_debate_records_positions_for_both_phases():
    members = [Member(name=n, provider_name="mock", model=f"mock-{n}") for n in "ABC"]
    providers = {m.name: MockProvider(model=m.model, latency_ms=0) for m in members}
    hansard = await Parliament(members, providers).ask("Postgres or Mongo?")

    for r in hansard.first_reading:
        assert r.position is not None and r.position.changed_mind is None
    for r in hansard.debate:
        assert r.position is not None and r.position.changed_mind is False


def test_positions_round_trip_and_old_records_load():
    hansard = Hansard(
        bill=Bill(content="q"),
        members=[Member(name="A", provider_name="mock", model="m")],
        first_reading=[
            Response("A", "x", "first_reading", position=Position("Use Postgres.")),
        ],
        debate=[Response("A", "y", "debate", position=Position("Use Mongo.", True))],
        synthesis=Synthesis(speaker_name="A"),
    )
    data = json.loads(hansard.to_json())
    assert data["debate"][0]["position"] == {"stance": "Use Mongo.", "changed_mind": True}
    assert Hansard.from_dict(data) == hansard

    for phase in ("first_reading", "debate"):
        for response in data[phase]:
            del response["position"]
    old = Hansard.from_dict(data)
    assert [r.position for r in old.first_reading + old.debate] == [None, None]
