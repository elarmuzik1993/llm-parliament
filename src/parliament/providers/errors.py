"""Human-readable error formatting for provider exceptions."""

from __future__ import annotations

import re


def format_provider_error(exc: BaseException) -> str:
    """Convert a raw provider exception into a concise, actionable one-liner.

    Handles common patterns from Ollama (via openai SDK), OpenAI, Anthropic,
    and Google providers. Falls back to a shortened repr for unknown errors.
    """
    raw = str(exc)
    exc_type = type(exc).__name__

    # ── Timeout ──────────────────────────────────────────────────────────────
    if exc_type in ("ReadTimeout", "ConnectTimeout", "TimeoutError") or "timed out" in raw.lower():
        return "Request timed out — model took too long to respond. Try a smaller model or increase the timeout."

    # ── Connection / not running ──────────────────────────────────────────────
    if exc_type in ("ConnectError", "ConnectionRefusedError") or "connection refused" in raw.lower():
        return "Could not connect to Ollama — is it running? Start with `ollama serve`."

    # ── Ollama OOM ────────────────────────────────────────────────────────────
    oom_match = re.search(r"model requires more system memory \(([^)]+)\)", raw)
    if oom_match:
        needed = oom_match.group(1)
        return f"Out of memory — model needs {needed} of RAM. Try a smaller/quantised model."
    if "out of memory" in raw.lower() or "oom" in raw.lower():
        return "Out of memory — model is too large for available RAM. Try a smaller model."

    # ── Rate limits (HTTP 429) ────────────────────────────────────────────────
    if "429" in raw or "rate limit" in raw.lower() or "quota" in raw.lower():
        return "Rate limit or quota exceeded — wait a moment, then retry. Check your provider billing."

    # ── Auth / API key (HTTP 401 / 403) ──────────────────────────────────────
    if "401" in raw or "403" in raw or "authentication" in raw.lower() or "api key" in raw.lower():
        return "Authentication failed — check your API key in config."

    # ── Model not found ───────────────────────────────────────────────────────
    if "404" in raw or "model not found" in raw.lower() or "does not exist" in raw.lower():
        return "Model not found — check the model name in your config, or run `ollama pull <model>`."

    # ── Context length exceeded ───────────────────────────────────────────────
    if "context" in raw.lower() and ("length" in raw.lower() or "window" in raw.lower() or "exceed" in raw.lower()):
        return "Prompt exceeded model context window — try a shorter question or a model with larger context."

    # ── Generic API error with status code ───────────────────────────────────
    status_match = re.search(r"\b(5\d{2})\b", raw)
    if status_match:
        code = status_match.group(1)
        return f"Provider returned HTTP {code} (server error) — try again in a moment."

    # ── Fallback: shorten the raw message to one line ─────────────────────────
    first_line = raw.splitlines()[0] if raw else exc_type
    if len(first_line) > 120:
        first_line = first_line[:117] + "…"
    return f"{exc_type}: {first_line}" if first_line and first_line != exc_type else exc_type
