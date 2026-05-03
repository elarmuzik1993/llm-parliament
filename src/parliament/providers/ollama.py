"""Ollama provider — local models via OpenAI-compatible API."""

from __future__ import annotations

from parliament.providers.base import Provider

DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self._base_url = base_url
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        """Lazy init — only import openai when actually used."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key="ollama",
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
