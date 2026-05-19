"""Google (Gemini) provider."""

from __future__ import annotations

from parliament.providers.base import Provider


class GoogleProvider(Provider):
    name = "google"

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate(self, prompt: str, system: str | None = None) -> str:
        client = self._get_client()

        config = {}
        if system:
            config["system_instruction"] = system
        if self._timeout is not None:
            config["http_options"] = {"timeout": self._timeout}

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text
