"""Tests for format_provider_error() and is_fatal_provider_error()."""

from parliament.providers.errors import format_provider_error, is_fatal_provider_error


def _exc(msg: str, cls=Exception) -> Exception:
    return cls(msg)


def test_ollama_oom_with_size():
    msg = "model requires more system memory (31.9 GiB) to load"
    result = format_provider_error(_exc(msg))
    assert "31.9 GiB" in result
    assert "smaller" in result.lower() or "memory" in result.lower()


def test_ollama_oom_generic():
    result = format_provider_error(_exc("out of memory"))
    assert "memory" in result.lower()
    assert "smaller" in result.lower()


def test_timeout_by_type():
    class ReadTimeout(Exception):
        pass
    result = format_provider_error(ReadTimeout("timed out"))
    assert "timed out" in result.lower() or "timeout" in result.lower()


def test_timeout_by_message():
    result = format_provider_error(_exc("request timed out after 60s"))
    assert "timed out" in result.lower() or "timeout" in result.lower()


def test_connection_refused():
    result = format_provider_error(ConnectionRefusedError("connection refused"))
    assert "ollama" in result.lower() or "connect" in result.lower()


def test_rate_limit_429():
    result = format_provider_error(_exc("HTTP 429: Too Many Requests"))
    assert "rate limit" in result.lower() or "quota" in result.lower() or "wait" in result.lower()


def test_rate_limit_by_text():
    result = format_provider_error(_exc("quota exceeded for this project"))
    assert "quota" in result.lower() or "rate limit" in result.lower()


def test_auth_401():
    result = format_provider_error(_exc("401 Unauthorized: invalid api key"))
    assert "api key" in result.lower() or "auth" in result.lower()


def test_model_not_found_404():
    result = format_provider_error(_exc("404: model 'llama99' does not exist"))
    assert "not found" in result.lower() or "model" in result.lower()


def test_context_length_exceeded():
    result = format_provider_error(_exc("prompt exceeds context window length of 8192 tokens"))
    assert "context" in result.lower()


def test_server_error_5xx():
    result = format_provider_error(_exc("HTTP 503 Service Unavailable"))
    assert "503" in result or "server error" in result.lower()


def test_unknown_error_truncated():
    long_msg = "A" * 200
    result = format_provider_error(_exc(long_msg))
    assert len(result) <= 140  # type name + truncated message


def test_unknown_error_single_line():
    result = format_provider_error(_exc("first line\nsecond line\nthird line"))
    assert "\n" not in result
    assert "first line" in result


def test_empty_exception():
    result = format_provider_error(_exc(""))
    assert result  # non-empty, doesn't crash


# ── is_fatal_provider_error ───────────────────────────────────────────────────

def test_fatal_quota_resource_exhausted():
    assert is_fatal_provider_error(_exc("429 RESOURCE_EXHAUSTED: You exceeded your current quota"))


def test_fatal_quota_keyword():
    assert is_fatal_provider_error(_exc("quota exceeded for this project"))


def test_fatal_billing():
    assert is_fatal_provider_error(_exc("429: check your billing details"))


def test_fatal_auth_401():
    assert is_fatal_provider_error(_exc("401 Unauthorized: invalid api key"))


def test_fatal_auth_403():
    assert is_fatal_provider_error(_exc("403 Forbidden: permission denied"))


def test_fatal_api_key_phrase():
    assert is_fatal_provider_error(_exc("Authentication failed: bad api key provided"))


def test_fatal_model_not_found_404():
    assert is_fatal_provider_error(_exc("404: model 'llama99' does not exist"))


def test_fatal_model_not_found_phrase():
    assert is_fatal_provider_error(_exc("model not found in registry"))


def test_transient_timeout_by_type():
    class ReadTimeout(Exception):
        pass
    assert not is_fatal_provider_error(ReadTimeout("timed out after 30s"))


def test_transient_timeout_by_message():
    assert not is_fatal_provider_error(_exc("request timed out after 60s"))


def test_transient_connection_refused():
    assert not is_fatal_provider_error(ConnectionRefusedError("connection refused"))


def test_transient_5xx():
    assert not is_fatal_provider_error(_exc("HTTP 503 Service Unavailable"))


def test_transient_bare_429_rate_limit():
    # A plain rate-limit 429 (no quota/billing language) is transient — will recover
    assert not is_fatal_provider_error(_exc("HTTP 429 Too Many Requests"))


def test_transient_oom():
    assert not is_fatal_provider_error(_exc("model requires more system memory (31 GiB)"))


def test_transient_generic_unknown():
    assert not is_fatal_provider_error(_exc("something unexpected happened"))
