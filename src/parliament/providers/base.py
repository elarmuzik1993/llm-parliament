"""Abstract base for all providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Provider(ABC):
    """A provider can generate text from a prompt.

    Implementations: OllamaProvider, AnthropicProvider, OpenAIProvider,
    GoogleProvider, MockProvider.
    """

    name: str  # "ollama", "anthropic", "openai", "google", "mock"
    model: str

    @property
    def base_url(self) -> str | None:
        """Configured endpoint, when exposed by the provider implementation."""
        return None

    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Send a prompt, return the model's text response."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r})"
