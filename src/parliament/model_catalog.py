"""Live model discovery for every supported provider.

Each fetch returns a PickerData(models, notice). When the fetch fails
(daemon down, no API key, network error), models is empty and notice
holds a human-readable hint the picker can display.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size_bytes: int


@dataclass(frozen=True)
class PickerData:
    models: list[str]
    notice: str | None = None
    ollama_models: tuple[OllamaModel, ...] = ()


def _ollama_tags_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return f"{base}/api/tags"


def fetch_ollama_models(base_url: str, timeout: float = 2.0) -> PickerData:
    url = _ollama_tags_url(base_url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return PickerData(
            models=[],
            notice=(
                f"Ollama daemon not reachable at {base_url}. "
                "Start it with: ollama serve"
            ),
        )
    except json.JSONDecodeError:
        return PickerData(models=[], notice=f"Ollama returned malformed JSON at {url}")
    ollama_models = tuple(
        sorted(
            (
                OllamaModel(name=str(m["name"]), size_bytes=int(m.get("size") or 0))
                for m in payload.get("models", [])
                if isinstance(m, dict) and m.get("name")
            ),
            key=lambda m: m.name,
        )
    )
    names = [m.name for m in ollama_models]
    if not names:
        return PickerData(
            models=[],
            notice="No Ollama models installed. Pull one: ollama pull llama3.1",
        )
    return PickerData(models=names, notice=None, ollama_models=ollama_models)


def _no_key_notice(provider: str, env_var: str) -> str:
    return (
        f"No API key for {provider}. Set one with: "
        f"parliament keys set {provider} <key>  (or {env_var} env var)"
    )


def _http_get_json(req: urllib.request.Request, timeout: float) -> Any:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass(frozen=True)
class OpenAICompatible:
    """A provider that speaks the OpenAI API at a different address.

    Groq, Mistral and OpenRouter all serve `GET {base_url}/models` with the
    same `{"data": [{"id": ...}]}` shape OpenAI does, so discovery is the same
    request against a different host -- there is no second client to write.

    This registry is the single place that knows each vendor's address and the
    environment variable its key lives in -- the model picker reads it for
    discovery, and the client factory reads it for the vendors listed in
    `providers._OPENAI_COMPATIBLE_PROVIDERS`. A row here is not by itself
    enough to make a name usable as a `provider:` value.
    """

    base_url: str
    env_var: str


OPENAI_COMPATIBLE: dict[str, OpenAICompatible] = {
    "openai": OpenAICompatible("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "groq": OpenAICompatible("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": OpenAICompatible("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "openrouter": OpenAICompatible("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


def fetch_openai_compatible_models(
    provider: str,
    api_key: str | None,
    timeout: float = DEFAULT_TIMEOUT,
) -> PickerData:
    spec = OPENAI_COMPATIBLE.get(provider)
    if spec is None:
        return PickerData(models=[], notice=f"Unknown provider: {provider}")
    if not api_key:
        return PickerData(models=[], notice=_no_key_notice(provider, spec.env_var))
    req = urllib.request.Request(
        f"{spec.base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        payload = _http_get_json(req, timeout)
    except urllib.error.HTTPError as e:
        return PickerData(models=[], notice=f"{provider} request failed: HTTP {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return PickerData(models=[], notice=f"{provider} request failed: {type(e).__name__}: {e}")
    ids = [
        str(m["id"]) for m in payload.get("data", [])
        if isinstance(m, dict) and m.get("id")
    ]
    return PickerData(models=sorted(ids), notice=None)


def fetch_openai_models(api_key: str | None, timeout: float = DEFAULT_TIMEOUT) -> PickerData:
    return fetch_openai_compatible_models("openai", api_key, timeout)


def fetch_anthropic_models(api_key: str | None, timeout: float = DEFAULT_TIMEOUT) -> PickerData:
    if not api_key:
        return PickerData(models=[], notice=_no_key_notice("anthropic", "ANTHROPIC_API_KEY"))
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        payload = _http_get_json(req, timeout)
    except urllib.error.HTTPError as e:
        return PickerData(models=[], notice=f"anthropic request failed: HTTP {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return PickerData(models=[], notice=f"anthropic request failed: {type(e).__name__}: {e}")
    ids = [
        str(m["id"]) for m in payload.get("data", [])
        if isinstance(m, dict) and m.get("id")
    ]
    return PickerData(models=sorted(ids), notice=None)


def fetch_google_models(api_key: str | None, timeout: float = DEFAULT_TIMEOUT) -> PickerData:
    if not api_key:
        return PickerData(models=[], notice=_no_key_notice("google", "GOOGLE_API_KEY"))
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models?key="
        + urllib.parse.quote(api_key)
    )
    req = urllib.request.Request(url)
    try:
        payload = _http_get_json(req, timeout)
    except urllib.error.HTTPError as e:
        return PickerData(models=[], notice=f"google request failed: HTTP {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return PickerData(models=[], notice=f"google request failed: {type(e).__name__}: {e}")
    names: list[str] = []
    for m in payload.get("models", []):
        if not isinstance(m, dict):
            continue
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        raw = str(m.get("name", ""))
        name = raw.removeprefix("models/")
        if name:
            names.append(name)
    return PickerData(models=sorted(names), notice=None)


def openai_compatible_key(provider: str) -> str | None:
    """The key to discover `provider`'s models with.

    For vendors with no `parliament keys set` home (the discovery-only rows
    `groq` and `mistral`), falling back to `OPENAI_API_KEY` keeps the picker
    consistent with `provider: openai + base_url`, where the same env var is
    what the OpenAI SDK actually uses anyway.

    For vendors that do have their own key entry in `KEY_PROVIDERS`
    (`openrouter`), the fallback is deliberately not applied: it exists so the
    picker reports "no key" to anyone whose config works, and OpenRouter's
    works on its own variable (#48). Reaching `OPENAI_API_KEY` here would set
    up the same leak `providers._create_openai_compatible` now refuses.
    """
    spec = OPENAI_COMPATIBLE.get(provider)
    if spec is None:
        return None
    # Local import: `config` imports `providers`, which imports this module.
    # A top-level import here would form a cycle at module load time.
    from parliament.config import KEY_PROVIDERS
    if provider in KEY_PROVIDERS:
        return os.environ.get(spec.env_var)
    return os.environ.get(spec.env_var) or os.environ.get("OPENAI_API_KEY")


def _ollama_base_url(config: dict[str, Any] | None) -> str:
    if not isinstance(config, dict):
        return "http://localhost:11434/v1"
    providers = config.get("providers", {}) if isinstance(config, dict) else {}
    ollama_cfg = providers.get("ollama", {}) if isinstance(providers, dict) else {}
    return str(ollama_cfg.get("base_url") or "http://localhost:11434/v1")


def picker_data_for(provider: str, config: dict[str, Any] | None = None) -> PickerData:
    """Return the live PickerData for the given provider."""
    if provider == "ollama":
        return fetch_ollama_models(_ollama_base_url(config))
    if provider in OPENAI_COMPATIBLE:
        return fetch_openai_compatible_models(provider, openai_compatible_key(provider))
    if provider == "anthropic":
        return fetch_anthropic_models(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "google":
        return fetch_google_models(os.environ.get("GOOGLE_API_KEY"))
    if provider == "mock":
        return PickerData(models=["mock-v1", "mock-v2", "mock-v3"], notice=None)
    return PickerData(models=[], notice=f"Unknown provider: {provider}")
