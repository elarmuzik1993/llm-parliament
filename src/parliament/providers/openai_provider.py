"""OpenAI (GPT) provider."""

from __future__ import annotations

from parliament.providers.base import Provider


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

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content
