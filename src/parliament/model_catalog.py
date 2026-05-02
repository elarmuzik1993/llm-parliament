"""Live model discovery for providers (Ollama today)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def _ollama_tags_url(base_url: str) -> str:
    """Convert an OpenAI-compatible Ollama base URL to its native /api/tags."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return f"{base}/api/tags"


def fetch_ollama_models(base_url: str, timeout: float = 2.0) -> list[str] | None:
    """Return locally-installed Ollama model names, or None if unreachable.

    Hits the daemon's native /api/tags endpoint, which returns
    {"models": [{"name": "llama3:latest", ...}, ...]}.
    """
    url = _ollama_tags_url(base_url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    models = payload.get("models", [])
    names = [str(m.get("name")) for m in models if isinstance(m, dict) and m.get("name")]
    return sorted(names)
