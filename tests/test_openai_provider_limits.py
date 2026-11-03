"""OpenAIProvider output cap and empty-reply handling -- issue #99."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from parliament.providers.openai_provider import MAX_OUTPUT_TOKENS, OpenAIProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _provider(base_url=None, content="An answer.", finish_reason="stop"):
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message, finish_reason=finish_reason)
        return SimpleNamespace(choices=[choice])

    provider = OpenAIProvider(model="test-model", api_key="k", base_url=base_url)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return provider, calls


async def test_native_openai_sends_max_completion_tokens():
    provider, calls = _provider(base_url=None)
    await provider.generate("q")
    assert calls[0]["max_completion_tokens"] == MAX_OUTPUT_TOKENS
    assert "max_tokens" not in calls[0]


async def test_compatible_endpoint_sends_max_tokens():
    provider, calls = _provider(base_url=OPENROUTER_BASE_URL)
    await provider.generate("q")
    assert calls[0]["max_tokens"] == MAX_OUTPUT_TOKENS
    assert "max_completion_tokens" not in calls[0]


async def test_empty_reply_at_length_limit_raises():
    provider, _ = _provider(content="", finish_reason="length")
    with pytest.raises(RuntimeError, match="16,384-token output limit") as exc:
        await provider.generate("q")
    assert "test-model" in str(exc.value)


async def test_none_reply_raises():
    provider, _ = _provider(content=None, finish_reason="stop")
    with pytest.raises(RuntimeError, match="test-model returned no text"):
        await provider.generate("q")


async def test_normal_reply_returned_unchanged_with_system_prompt():
    provider, calls = _provider(content="  An answer.\n")
    assert await provider.generate("q", system="be brief") == "  An answer.\n"
    assert calls[0]["model"] == "test-model"
    assert calls[0]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "q"},
    ]
