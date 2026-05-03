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
class PickerData:
    models: list[str]
    notice: str | None = None


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
    names = sorted(
        str(m["name"]) for m in payload.get("models", [])
        if isinstance(m, dict) and m.get("name")
    )
    if not names:
        return PickerData(
            models=[],
            notice="No Ollama models installed. Pull one: ollama pull llama3.1",
        )
    return PickerData(models=names, notice=None)


def _no_key_notice(provider: str, env_var: str) -> str:
    return (
        f"No API key for {provider}. Set one with: "
        f"parliament keys set {provider} <key>  (or {env_var} env var)"
    )


def _http_get_json(req: urllib.request.Request, timeout: float) -> Any:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_openai_models(api_key: str | None, timeout: float = DEFAULT_TIMEOUT) -> PickerData:
    if not api_key:
        return PickerData(models=[], notice=_no_key_notice("openai", "OPENAI_API_KEY"))
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        payload = _http_get_json(req, timeout)
    except urllib.error.HTTPError as e:
        return PickerData(models=[], notice=f"openai request failed: HTTP {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return PickerData(models=[], notice=f"openai request failed: {type(e).__name__}: {e}")
    ids = [
        str(m["id"]) for m in payload.get("data", [])
        if isinstance(m, dict) and m.get("id")
    ]
    return PickerData(models=sorted(ids), notice=None)


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
    if provider == "openai":
        return fetch_openai_models(os.environ.get("OPENAI_API_KEY"))
    if provider == "anthropic":
        return fetch_anthropic_models(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "google":
        return fetch_google_models(os.environ.get("GOOGLE_API_KEY"))
    if provider == "mock":
        return PickerData(models=["mock-v1", "mock-v2", "mock-v3"], notice=None)
    return PickerData(models=[], notice=f"Unknown provider: {provider}")
