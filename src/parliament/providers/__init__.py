"""Provider registry — maps config strings to provider classes."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from parliament.model_catalog import OPENAI_COMPATIBLE
from parliament.providers.base import Provider
from parliament.providers.errors import format_provider_error, is_fatal_provider_error
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

# OpenAI-compatible vendors served by `OpenAIProvider` at their own address.
# `model_catalog.OPENAI_COMPATIBLE` already holds each one's address and key
# variable -- it was added for the model picker -- so a name only needs listing
# here to become a usable `provider:` value. A registry row is deliberately not
# enough on its own: `groq` and `mistral` stay discovery-only, which is the
# behaviour the README documents, so this tuple is the explicit opt-in.
_OPENAI_COMPATIBLE_PROVIDERS = ("openrouter",)

# Every name in the tuple above shares this one client class.
_OPENAI_PROVIDER = ("parliament.providers.openai_provider", "OpenAIProvider")


def _load_provider_class(
    provider_name: str, module_path: str, class_name: str, model: str, **kwargs
) -> Provider:
    try:
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(model=model, **kwargs)
    except ImportError as err:
        # `from err` on purpose: the original names the module that actually
        # failed to import, which separates "the SDK is not installed" from
        # "the SDK is installed and one of its own imports is broken".
        raise ImportError(
            f"Cloud provider '{provider_name}' requires its SDK. "
            f"Install it: pip install llm-parliament[{provider_name}]"
        ) from err


def _create_openai_compatible(provider_name: str, model: str, **kwargs) -> Provider:
    """Build an OpenAI-compatible provider from its `model_catalog` row.

    The row supplies the address; the caller supplies the key (or one is read
    from the row's own environment variable). A missing key is a hard error,
    not a silent fallback -- `AsyncOpenAI(api_key=None)` reads `OPENAI_API_KEY`
    from the process environment for us, which would post an OpenAI credential
    to a different vendor (#48). Discovery (`openai_compatible_key()` in
    `model_catalog`) is allowed to borrow; construction here is not.
    """
    spec = OPENAI_COMPATIBLE.get(provider_name)
    if spec is None:
        raise ValueError(f"Unknown provider: '{provider_name}'")
    kwargs.setdefault("base_url", spec.base_url)
    if "api_key" not in kwargs:
        key = os.environ.get(spec.env_var)
        if not key:
            raise ValueError(
                f"Provider '{provider_name}' needs {spec.env_var}. "
                f"Set it with: parliament keys set {provider_name} <key>"
            )
        kwargs["api_key"] = key
    return _load_provider_class(
        provider_name, _OPENAI_PROVIDER[0], _OPENAI_PROVIDER[1], model, **kwargs
    )


def create_provider(provider_name: str, model: str, **kwargs) -> Provider:
    """Factory: config string → Provider instance.

    Raises ImportError with install hint if a cloud SDK is missing.
    """
    if provider_name == "mock":
        return MockProvider(model=model)
    if provider_name == "ollama":
        return OllamaProvider(model=model, **kwargs)

    if provider_name in _OPENAI_COMPATIBLE_PROVIDERS:
        return _create_openai_compatible(provider_name, model, **kwargs)

    if provider_name in _CLOUD_PROVIDERS:
        module_path, class_name = _CLOUD_PROVIDERS[provider_name]
        return _load_provider_class(provider_name, module_path, class_name, model, **kwargs)

    raise ValueError(f"Unknown provider: '{provider_name}'")


__all__ = [
    "Provider",
    "MockProvider",
    "OllamaProvider",
    "create_provider",
    "format_provider_error",
    "is_fatal_provider_error",
]
