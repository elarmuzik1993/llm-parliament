"""`parliament mcp`: the `debate` (#9), `ask` and `consult` (#99) tools for coding agents.

The return shape, what is saved, progress, failures and the one-at-a-time rule
follow the design note and its follow-up on #9.
"""

import asyncio
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

pytest.importorskip("mcp")

from mcp.client import Client

from parliament import cli
from parliament.core.parliament import Parliament
from parliament.core.types import Hansard, Member
from parliament.mcp_server import (
    ANSWER_CHARS,
    ASK_SYSTEM,
    SCHEMA_VERSION,
    build_result,
    create_server,
    is_mock_only,
    save_hansard_json,
)
from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider


def _panel(n: int = 2, latency_ms: int = 0):
    members = [Member(name=f"M{i}", provider_name="mock", model=f"mock-{i}") for i in range(n)]
    providers = {m.name: MockProvider(model=m.model, latency_ms=latency_ms) for m in members}
    return members, providers


class FailingProvider(Provider):
    name = "failing"

    def __init__(self) -> None:
        self.model = "failing"

    async def generate(self, prompt: str, system: str | None = None) -> str:
        raise ConnectionError("provider unreachable")


class CountingProvider(MockProvider):
    """Tracks how many generate() calls are in flight across every debate."""

    active = 0
    peak = 0

    async def generate(self, prompt: str, system: str | None = None) -> str:
        cls = type(self)
        cls.active += 1
        cls.peak = max(cls.peak, cls.active)
        try:
            await asyncio.sleep(0.02)
            return await super().generate(prompt, system)
        finally:
            cls.active -= 1


async def _mock_hansard() -> Hansard:
    members, providers = _panel()
    return await Parliament(members, providers).ask("Postgres or Mongo?")


async def test_result_is_the_summary_and_verdict_without_transcripts(tmp_path):
    hansard = await _mock_hansard()
    result = build_result(hansard, tmp_path / "h.json")

    assert set(result) == {"schema", "summary", "verdict", "members", "hansard_path"}
    assert result["schema"] == SCHEMA_VERSION
    assert result["summary"]["contested"] is False
    assert result["summary"]["contested_on"] == ""
    assert result["summary"]["degraded"] is False
    assert result["summary"]["warnings"] == []
    assert result["hansard_path"] == str(tmp_path / "h.json")
    # The verdict is the synthesis minus what the summary already carries and
    # the raw Speaker text; the members' answers stay in the saved file.
    assert "raw" not in result["verdict"]
    assert "contested" not in result["verdict"]
    assert result["verdict"]["recommendation"] == hansard.synthesis.recommendation
    assert "first_reading" not in result and "debate" not in result
    assert [m["name"] for m in result["members"]] == ["M0", "M1"]


async def test_summary_positions_are_the_final_self_reported_ones(tmp_path):
    hansard = await _mock_hansard()
    positions = build_result(hansard, tmp_path / "h.json")["summary"]["positions"]
    assert [p["member"] for p in positions] == ["M0", "M1"]
    assert all(p["changed_mind"] is False and p["stance"] for p in positions)


async def test_a_member_without_a_position_line_has_a_null_stance(tmp_path):
    hansard = await _mock_hansard()
    hansard.debate[0].position = None
    positions = build_result(hansard, tmp_path / "h.json")["summary"]["positions"]
    assert positions[0] == {"member": "M0", "stance": None, "changed_mind": None}


async def test_full_hansard_is_saved_as_json_and_reads_back(tmp_path):
    hansard = await _mock_hansard()
    path = save_hansard_json(hansard, tmp_path / "hansards")
    assert path.parent == tmp_path / "hansards" and path.suffix == ".json"
    assert Hansard.from_dict(json.loads(path.read_text(encoding="utf-8"))) == hansard


def test_mock_only_panel_is_detected():
    members, _ = _panel()
    assert is_mock_only(members)
    assert not is_mock_only([*members, Member("Real", "openrouter", "openai/gpt-5.1")])


def test_tool_description_states_the_cost():
    members, providers = _panel(3)
    server = create_server(members, providers)
    tool = asyncio.run(server.list_tools())[0]
    assert tool.name == "debate"
    assert "7 model calls" in tool.description
    assert "costs money" in tool.description


async def test_debate_tool_returns_the_result_and_reports_progress(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, save_dir=tmp_path)
    seen: list[tuple[float, str | None]] = []

    async def on_progress(progress, total, message):
        seen.append((progress, message))

    async with Client(server) as client:
        result = await client.call_tool(
            "debate", {"question": "Postgres or Mongo?"}, progress_callback=on_progress
        )

    assert not result.is_error
    data = result.structured_content
    assert data["schema"] == SCHEMA_VERSION
    assert data["summary"]["contested"] is False
    saved = json.loads(Path(data["hansard_path"]).read_text(encoding="utf-8"))
    assert saved["bill"]["content"] == "Postgres or Mongo?"
    progress = [p for p, _ in seen]
    assert progress == sorted(progress) and len(set(progress)) == len(progress)
    assert any("Division" in (m or "") for _, m in seen)


async def test_a_failed_debate_is_a_tool_error_not_a_verdict(tmp_path):
    members, _ = _panel()
    providers = {m.name: FailingProvider() for m in members}
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("debate", {"question": "Which?"})
    assert result.is_error
    assert "Not enough members responded" in result.content[0].text
    assert list(tmp_path.iterdir()) == []


async def test_debates_run_one_at_a_time(tmp_path):
    CountingProvider.active = CountingProvider.peak = 0
    members, _ = _panel()
    providers = {m.name: CountingProvider(model=m.model, latency_ms=0) for m in members}
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        results = await asyncio.gather(
            client.call_tool("debate", {"question": "One?"}),
            client.call_tool("debate", {"question": "Two?"}),
        )
    assert not any(r.is_error for r in results)
    # One debate runs its two members in parallel; two debates at once would be 4.
    assert CountingProvider.peak == 2


async def test_a_waiting_call_keeps_reporting_progress(tmp_path):
    members, _ = _panel()
    providers = {m.name: MockProvider(model=m.model, latency_ms=60) for m in members}
    server = create_server(members, providers, save_dir=tmp_path, heartbeat_s=0.02)
    second: list[str | None] = []

    async def on_progress(progress, total, message):
        second.append(message)

    async with Client(server) as client:
        first = asyncio.create_task(client.call_tool("debate", {"question": "One?"}))
        await asyncio.sleep(0.01)
        await client.call_tool("debate", {"question": "Two?"}, progress_callback=on_progress)
        await first
    waiting = [m for m in second if m and "Waiting" in m]
    assert len(waiting) >= 2


def test_cli_refuses_a_mock_only_panel_without_the_mock_flag(monkeypatch):
    members, providers = _panel()
    monkeypatch.setattr(cli, "load_config", lambda _: {})
    monkeypatch.setattr(cli, "build_parliament_from_config", lambda _: (members, providers))
    result = CliRunner().invoke(cli.main, ["mcp"])
    assert result.exit_code != 0
    assert "mock" in result.stderr and "--mock" in result.stderr


def test_cli_says_how_to_install_the_extra_when_the_sdk_is_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "parliament.mcp_server", None)
    result = CliRunner().invoke(cli.main, ["mcp", "--mock"])
    assert result.exit_code != 0
    assert 'pip install "llm-parliament[mcp]"' in result.stderr


class RecordingProvider(MockProvider):
    def __init__(self, model: str = "rec") -> None:
        super().__init__(model=model, latency_ms=0)
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return "Use Postgres."


def _outside() -> tuple[Member, Provider]:
    return Member(name="Outside", provider_name="mock", model="mock-outside"), MockProvider(
        model="mock-outside", latency_ms=0
    )


def test_ask_is_listed_after_debate_and_names_every_model():
    members, providers = _panel(3)
    server = create_server(members, providers, outside_speaker=_outside())
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["debate", "ask", "consult"]
    ask = tools[1]
    for model in ["mock-0", "mock-1", "mock-2", "mock-outside"]:
        assert model in ask.description
    assert "outside Speaker" in ask.description
    assert "costs money" in ask.description


async def test_ask_returns_the_answer_and_saves_a_record(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "M1", "question": "Postgres or Mongo?"})

    assert not result.is_error
    data = result.structured_content
    assert data["schema"] == SCHEMA_VERSION
    assert (data["member"], data["provider"], data["model"]) == ("M1", "mock", "mock-1")
    assert "Postgres or Mongo?" in data["answer"]
    assert isinstance(data["duration_ms"], int)
    path = Path(data["record_path"])
    assert path.parent == tmp_path / "asks" and path.suffix == ".json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["question"] == "Postgres or Mongo?"
    assert saved["answer"] == data["answer"]
    assert saved["member"] == "M1" and saved["model"] == "mock-1"
    assert "timestamp" in saved and "duration_ms" in saved


async def test_ask_matches_member_names_case_insensitively(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "m0", "question": "Which?"})
    assert not result.is_error
    assert result.structured_content["member"] == "M0"


async def test_the_outside_speaker_can_be_asked(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, outside_speaker=_outside(), save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "outside", "question": "Which?"})
    assert not result.is_error
    assert result.structured_content["model"] == "mock-outside"


async def test_a_panel_member_wins_a_name_clash_with_the_outside_speaker(tmp_path):
    members, providers = _panel()
    clash = (Member(name="M0", provider_name="mock", model="mock-outside"), _outside()[1])
    server = create_server(members, providers, outside_speaker=clash, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "M0", "question": "Which?"})
    assert result.structured_content["model"] == "mock-0"


async def test_asking_an_unknown_member_lists_the_valid_names(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, outside_speaker=_outside(), save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "Nobody", "question": "Which?"})
    assert result.is_error
    message = result.content[0].text
    assert "Nobody" in message
    assert all(name in message for name in ["M0", "M1", "Outside"])
    assert list(tmp_path.iterdir()) == []


async def test_a_failed_ask_is_a_tool_error_naming_the_member(tmp_path):
    members, providers = _panel()
    providers["M1"] = FailingProvider()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "M1", "question": "Which?"})
    assert result.is_error
    assert "M1 failed" in result.content[0].text
    assert list(tmp_path.iterdir()) == []


class EmptyProvider(MockProvider):
    async def generate(self, prompt: str, system: str | None = None) -> str:
        return ""


async def test_an_empty_answer_is_a_tool_error_not_an_answer(tmp_path):
    members, providers = _panel()
    providers["M1"] = EmptyProvider(model="mock-1", latency_ms=0)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "M1", "question": "Which?"})
    assert result.is_error
    assert "M1 returned no text" in result.content[0].text
    assert list(tmp_path.iterdir()) == []


async def test_ask_sends_the_question_as_written_with_the_ask_system_prompt(tmp_path):
    members, providers = _panel()
    recorder = RecordingProvider()
    providers["M0"] = recorder
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("ask", {"member": "M0", "question": "Postgres or Mongo?"})
    assert result.structured_content["answer"] == "Use Postgres."
    assert recorder.calls == [("Postgres or Mongo?", ASK_SYSTEM)]


async def test_ask_does_not_wait_for_a_running_debate(tmp_path):
    members, providers = _panel(latency_ms=200)
    members.append(Member(name="Fast", provider_name="mock", model="mock-fast"))
    providers["Fast"] = MockProvider(model="mock-fast", latency_ms=0)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        debate = asyncio.create_task(client.call_tool("debate", {"question": "One?"}))
        await asyncio.sleep(0.02)
        result = await client.call_tool("ask", {"member": "Fast", "question": "Two?"})
        assert not result.is_error
        assert not debate.done()
        await debate


def _saved_files(tmp_path):
    return [p for p in tmp_path.rglob("*") if p.is_file()]


def test_consult_is_listed_after_ask_and_states_the_cost():
    members, providers = _panel(3)
    server = create_server(members, providers, outside_speaker=_outside())
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["debate", "ask", "consult"]
    consult = tools[2]
    for model in ["mock-0", "mock-1", "mock-2"]:
        assert model in consult.description
    # The outside Speaker is not a debater, so it is not consulted.
    assert "mock-outside" not in consult.description
    assert "3 model calls" in consult.description
    assert "costs money" in consult.description


async def test_consult_asks_the_whole_panel_by_default(tmp_path):
    members, providers = _panel(3)
    server = create_server(members, providers, outside_speaker=_outside(), save_dir=tmp_path)
    seen: list[str | None] = []

    async def on_progress(progress, total, message):
        seen.append(message)

    async with Client(server) as client:
        result = await client.call_tool(
            "consult", {"question": "Postgres or Mongo?"}, progress_callback=on_progress
        )

    assert not result.is_error
    data = result.structured_content
    assert data["schema"] == SCHEMA_VERSION
    assert set(data) == {"schema", "positions", "answers", "degraded", "warnings", "record_path"}
    assert [a["member"] for a in data["answers"]] == ["M0", "M1", "M2"]
    assert [p["member"] for p in data["positions"]] == ["M0", "M1", "M2"]
    first = data["answers"][0]
    assert (first["provider"], first["model"], first["truncated"]) == ("mock", "mock-0", False)
    # The debate's First Reading prompt, so the answers compare with a debate's.
    assert "You are one of 3 AI analysts" in first["answer"]
    assert isinstance(first["duration_ms"], int)
    assert data["degraded"] is False and data["warnings"] == []
    assert sorted(m for m in seen if m) == [f"First Reading: M{i} done" for i in range(3)]

    path = Path(data["record_path"])
    assert path.parent == tmp_path / "consults" and path.suffix == ".json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["question"] == "Postgres or Mongo?"
    assert saved["members"] == ["M0", "M1", "M2"]
    assert [a["answer"] for a in saved["answers"]] == [a["answer"] for a in data["answers"]]
    assert saved["positions"] == data["positions"]
    assert saved["degraded"] is False and "timestamp" in saved


async def test_consult_positions_come_from_the_position_line(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("consult", {"question": "Which?"})
    positions = result.structured_content["positions"]
    assert positions == [
        {"member": "M0", "stance": "Mock mock-0 recommends the simplest option."},
        {"member": "M1", "stance": "Mock mock-1 recommends the simplest option."},
    ]


async def test_consult_asks_only_the_named_members(tmp_path):
    members, providers = _panel(3)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool(
            "consult", {"question": "Which?", "members": ["m2", "M0", "M2 "]}
        )
    assert not result.is_error
    data = result.structured_content
    # Panel order, each member once.
    assert [a["member"] for a in data["answers"]] == ["M0", "M2"]
    assert data["degraded"] is False
    saved = json.loads(Path(data["record_path"]).read_text(encoding="utf-8"))
    assert saved["members"] == ["M0", "M2"]


async def test_consulting_one_member_points_to_ask(tmp_path):
    members, providers = _panel(3)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("consult", {"question": "Which?", "members": ["M1", "m1"]})
    assert result.is_error
    assert "use ask" in result.content[0].text
    assert _saved_files(tmp_path) == []


async def test_consulting_an_unknown_member_lists_the_panel(tmp_path):
    members, providers = _panel(3)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool(
            "consult", {"question": "Which?", "members": ["M0", "Nobody"]}
        )
    assert result.is_error
    message = result.content[0].text
    assert "Nobody" in message
    assert all(name in message for name in ["M0", "M1", "M2"])
    assert _saved_files(tmp_path) == []


async def test_the_outside_speaker_cannot_be_consulted(tmp_path):
    members, providers = _panel()
    server = create_server(members, providers, outside_speaker=_outside(), save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool(
            "consult", {"question": "Which?", "members": ["M0", "Outside"]}
        )
    assert result.is_error
    message = result.content[0].text
    assert "outside Speaker" in message and "ask it with ask" in message
    assert _saved_files(tmp_path) == []


async def test_a_member_lost_in_a_consult_is_a_warning_not_an_error(tmp_path):
    members, providers = _panel(3)
    providers["M1"] = FailingProvider()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("consult", {"question": "Which?"})
    assert not result.is_error
    data = result.structured_content
    assert [a["member"] for a in data["answers"]] == ["M0", "M2"]
    assert data["degraded"] is True
    assert len(data["warnings"]) == 1
    warning = data["warnings"][0]
    assert warning["kind"] == "member_failed"
    assert warning["message"].startswith("First Reading: M1: ")
    saved = json.loads(Path(data["record_path"]).read_text(encoding="utf-8"))
    assert saved["degraded"] is True and saved["warnings"] == data["warnings"]


async def test_a_consult_with_too_few_answers_is_a_tool_error(tmp_path):
    members, providers = _panel(3)
    providers["M0"] = FailingProvider()
    providers["M2"] = FailingProvider()
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("consult", {"question": "Which?"})
    assert result.is_error
    assert "The consultation failed" in result.content[0].text
    assert "Not enough members responded" in result.content[0].text
    assert _saved_files(tmp_path) == []


class LongProvider(MockProvider):
    async def generate(self, prompt: str, system: str | None = None) -> str:
        return "x" * (ANSWER_CHARS + 100) + "\n\nPOSITION: Use Postgres."


async def test_a_long_answer_is_cut_in_the_result_and_kept_whole_in_the_record(tmp_path):
    members, providers = _panel()
    providers["M0"] = LongProvider(model="mock-0", latency_ms=0)
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        result = await client.call_tool("consult", {"question": "Which?"})
    data = result.structured_content
    long, short = data["answers"]
    assert len(long["answer"]) == ANSWER_CHARS and long["truncated"] is True
    assert short["truncated"] is False
    # The stance is read from the whole answer, not the cut one.
    assert data["positions"][0]["stance"] == "Use Postgres."
    saved = json.loads(Path(data["record_path"]).read_text(encoding="utf-8"))
    assert saved["answers"][0]["answer"].endswith("POSITION: Use Postgres.")
    assert len(saved["answers"][0]["answer"]) > ANSWER_CHARS


async def test_consult_waits_for_a_running_debate(tmp_path):
    CountingProvider.active = CountingProvider.peak = 0
    members, _ = _panel()
    providers = {m.name: CountingProvider(model=m.model, latency_ms=0) for m in members}
    server = create_server(members, providers, save_dir=tmp_path)
    async with Client(server) as client:
        results = await asyncio.gather(
            client.call_tool("debate", {"question": "One?"}),
            client.call_tool("consult", {"question": "Two?"}),
        )
    assert not any(r.is_error for r in results)
    # Each runs its two members in parallel; both at once would be 4.
    assert CountingProvider.peak == 2


async def test_a_waiting_consult_keeps_reporting_progress(tmp_path):
    members, _ = _panel()
    providers = {m.name: MockProvider(model=m.model, latency_ms=60) for m in members}
    server = create_server(members, providers, save_dir=tmp_path, heartbeat_s=0.02)
    second: list[str | None] = []

    async def on_progress(progress, total, message):
        second.append(message)

    async with Client(server) as client:
        first = asyncio.create_task(client.call_tool("debate", {"question": "One?"}))
        await asyncio.sleep(0.01)
        await client.call_tool("consult", {"question": "Two?"}, progress_callback=on_progress)
        await first
    waiting = [m for m in second if m and "Waiting" in m]
    assert len(waiting) >= 2
