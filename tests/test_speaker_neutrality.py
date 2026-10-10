"""The Speaker should not judge its own position (#73).

Two guards: the Division prompt hides member names, and a config can name an
outside Speaker that did not debate.
"""

import pytest

from parliament.config import build_speaker_from_config
from parliament.core.parliament import Parliament
from parliament.core.types import Bill, Member, Response
from parliament.procedures.division import run_division
from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider
from parliament.tui import build_model_settings


class RecordingProvider(Provider):
    name = "recording"

    def __init__(self, reply: str = "", fail: bool = False) -> None:
        self.model = "recording"
        self.reply = reply
        self.fail = fail
        self.prompts: list[str] = []

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise ConnectionError("judge unreachable")
        return self.reply


SYNTHESIS = (
    "CONSENSUS:\nMember 1 and Member 2 agree.\n\n"
    "SPLIT:\nMember 2 argued for B; Member 1's case for C is stronger.\n\n"
    "RISKS:\n- Timeline\n\n"
    "RECOMMENDATION:\nChoose C."
)


def _debate() -> list[Response]:
    return [
        Response(member_name="Claude", content="I pick C. Gemini is wrong.", phase="debate"),
        Response(member_name="Gemini", content="I pick B. Claude overlooks reads.", phase="debate"),
    ]


async def _divide(provider: Provider):
    speaker = Member(name="Claude", provider_name="mock", model="m")
    return await run_division(
        bill=Bill(content="Which option?"),
        members=[speaker],
        debate_responses=_debate(),
        speaker=speaker,
        speaker_provider=provider,
        on_progress=lambda event: None,
    )


async def test_division_prompt_hides_member_names():
    provider = RecordingProvider(reply=SYNTHESIS)
    await _divide(provider)
    prompt = provider.prompts[0]
    assert "Claude" not in prompt and "Gemini" not in prompt
    assert "Member 1" in prompt and "Member 2" in prompt
    assert "I pick B. Member 1 overlooks reads." in prompt


async def test_synthesis_puts_member_names_back():
    synthesis = await _divide(RecordingProvider(reply=SYNTHESIS))
    assert synthesis.consensus == "Claude and Gemini agree."
    assert synthesis.split == "Gemini argued for B; Claude's case for C is stronger."
    assert "Member 1" not in synthesis.raw


async def test_plural_labels_are_put_back_too():
    reply = SYNTHESIS.replace("Choose C.", "Members 1 and 2 choose C; Member 3 abstains.")
    synthesis = await _divide(RecordingProvider(reply=reply))
    assert synthesis.recommendation == "Claude and Gemini choose C; Member 3 abstains."


def _members_and_providers():
    members = [
        Member(name="Alpha", provider_name="mock", model="mock-v1", tier=2),
        Member(name="Beta", provider_name="mock", model="mock-v2", tier=2),
    ]
    providers = {m.name: MockProvider(model=m.model, latency_ms=0) for m in members}
    return members, providers


async def test_outside_speaker_writes_the_synthesis():
    members, providers = _members_and_providers()
    judge = RecordingProvider(reply=SYNTHESIS)
    outside = (Member(name="Judge", provider_name="mock", model="judge"), judge)
    hansard = await Parliament(members, providers, outside_speaker=outside).ask("Which?")
    assert hansard.synthesis.speaker_name == "Judge"
    assert len(judge.prompts) == 1
    assert [m.name for m in hansard.members] == ["Alpha", "Beta"]


async def test_failed_outside_speaker_falls_back_to_a_member():
    members, providers = _members_and_providers()
    outside = (
        Member(name="Judge", provider_name="mock", model="judge"),
        RecordingProvider(fail=True),
    )
    hansard = await Parliament(members, providers, outside_speaker=outside).ask("Which?")
    assert hansard.synthesis.speaker_name == "Alpha"


async def test_speaker_flag_naming_a_member_beats_the_outside_speaker():
    members, providers = _members_and_providers()
    judge = RecordingProvider(reply=SYNTHESIS)
    outside = (Member(name="Judge", provider_name="mock", model="judge"), judge)
    parliament = Parliament(members, providers, speaker_override="beta", outside_speaker=outside)
    hansard = await parliament.ask("Which?")
    assert hansard.synthesis.speaker_name == "Beta"
    assert judge.prompts == []


def _config(speaker=None):
    config = {
        "parliament": {
            "members": [
                {"name": "Alpha", "provider": "mock", "model": "mock-v1"},
                {"name": "Beta", "provider": "mock", "model": "mock-v2"},
            ]
        },
        "providers": {},
    }
    if speaker is not None:
        config["parliament"]["speaker"] = speaker
    return config


def test_no_speaker_in_config_means_no_outside_speaker():
    assert build_speaker_from_config(_config()) is None


def test_outside_speaker_is_built_from_config():
    built = build_speaker_from_config(_config({"provider": "mock", "model": "judge-v1"}))
    assert built is not None
    speaker, provider = built
    assert (speaker.name, speaker.provider_name, speaker.model) == ("Speaker", "mock", "judge-v1")
    assert provider.model == "judge-v1"


def test_outside_speaker_cannot_share_a_member_name():
    config = _config({"name": "alpha", "provider": "mock", "model": "judge-v1"})
    with pytest.raises(ValueError, match="Alpha"):
        build_speaker_from_config(config)


def test_settings_screen_shows_no_member_as_speaker_when_one_is_configured():
    rows = build_model_settings(_config({"provider": "mock", "model": "judge-v1"}))
    assert [row.role for row in rows] == ["Member", "Member"]
    rows = build_model_settings(_config({"provider": "mock", "model": "judge-v1"}), "Beta")
    assert [row.role for row in rows] == ["Member", "Speaker / member"]
