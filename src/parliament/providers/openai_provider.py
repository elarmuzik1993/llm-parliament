"""OpenAI (GPT) provider."""

from __future__ import annotations

from parliament.providers.base import Provider

# OpenRouter reserves credit for a request's output limit, and an unset limit
# reserves 65,536 tokens -- the cause of the HTTP 402s on a small balance.
# Reasoning tokens count against the limit too, so it is not set lower.
MAX_OUTPUT_TOKENS = 16_384


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        # An OpenAI-compatible endpoint -- Groq, Mistral, or anything else
        # speaking the same API at its own address. None means api.openai.com,
        # which is what the SDK does with base_url unset, so the default path
        # is untouched. OllamaProvider already worked this way.
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    @property
    def base_url(self) -> str | None:
        return self._base_url

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def generate(self, prompt: str, system: str | None = None) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # api.openai.com's reasoning models reject `max_tokens`; compatible
        # endpoints (OpenRouter, Groq, Mistral) take it.
        limit = (
            {"max_completion_tokens": MAX_OUTPUT_TOKENS}
            if self._base_url is None
            else {"max_tokens": MAX_OUTPUT_TOKENS}
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            **limit,
        )
        choice = response.choices[0]
        content = choice.message.content
        if not content:
            if choice.finish_reason == "length":
                raise RuntimeError(
                    f"{self.model} hit the {MAX_OUTPUT_TOKENS:,}-token output limit "
                    "before producing any text"
                )
            raise RuntimeError(f"{self.model} returned no text")
        return content
