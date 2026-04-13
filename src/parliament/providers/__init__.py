"""Provider registry — maps config strings to provider classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from parliament.providers.base import Provider
from parliament.providers.mock import MockProvider
from parliament.providers.ollama import OllamaProvider

if TYPE_CHECKING:
    pass

# Lazy imports for cloud providers — only fail when actually used
_CLOUD_PROVIDERS: dict[str, tuple[str, str]] = {
    "anthropic": ("parliament.providers.anthropic_provider", "AnthropicProvider"),
    "openai": ("parliament.providers.openai_provider", "OpenAIProvider"),
    "google": ("parliament.providers.google_provider", "GoogleProvider"),
}


def create_provider(provider_name: str, model: str, **kwargs) -> Provider:
    """Factory: config string → Provider instance.

    Raises ImportError with install hint if a cloud SDK is missing.
    """
    if provider_name == "mock":
        return MockProvider(model=model)
    if provider_name == "ollama":
        return OllamaProvider(model=model, **kwargs)

    if provider_name in _CLOUD_PROVIDERS:
        module_path, class_name = _CLOUD_PROVIDERS[provider_name]
        try:
            import importlib

            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            return cls(model=model, **kwargs)
        except ImportError:
            raise ImportError(
                f"Cloud provider '{provider_name}' requires its SDK. "
                f"Install it: pip install llm-parliament[{provider_name}]"
            )

    raise ValueError(f"Unknown provider: '{provider_name}'")


__all__ = [
    "Provider",
    "MockProvider",
    "OllamaProvider",
    "create_provider",
]
