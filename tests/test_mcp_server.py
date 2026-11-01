"""`parliament mcp`: one `debate` tool for coding agents (#9).

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
