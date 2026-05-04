"""Health-check logic for `parliament doctor`."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx
from rich.console import Console


@dataclass
class CheckResult:
    """Outcome of a single doctor check."""
    ok: bool                # False -> fail (exit 1) unless `warn` is True
    warn: bool = False      # True -> ok=True but render in yellow
    info: bool = False      # True -> ok=True but render in blue (e.g. "key not set")
    message: str = ""       # what to render after the symbol


def _check_python_version() -> CheckResult:
    # Use index access (works with both real version_info and test plain tuples).
    v = sys.version_info
    actual = f"{v[0]}.{v[1]}.{v[2]}"
    if (v[0], v[1]) >= (3, 11):
        return CheckResult(ok=True, message=f"Python {actual} (>=3.11 required)")
    return CheckResult(
        ok=False,
        message=f"Python {actual} - please upgrade to >=3.11",
    )


def _check_curses() -> CheckResult:
    try:
        import curses  # noqa: F401
        return CheckResult(ok=True, message="Curses available")
    except ImportError as e:
        return CheckResult(ok=False, message=f"Curses unavailable: {e}")


def _check_terminal_size() -> CheckResult:
    try:
        size = os.get_terminal_size()
    except OSError:
        return CheckResult(ok=True, warn=True, message="Terminal size unknown (not a TTY)")
    msg = f"Terminal: {size.columns}x{size.lines}"
    if size.columns >= 80 and size.lines >= 24:
        return CheckResult(ok=True, message=msg)
    return CheckResult(ok=True, warn=True, message=f"{msg} (recommended >=80x24)")


def _check_config() -> CheckResult:
    from parliament.config import USER_CONFIG, load_config

    load_config()  # triggers first-run copy if needed
    return CheckResult(
        ok=True,
        message=f"Config: {USER_CONFIG} (initialized)",
    )


PROVIDER_DISPLAY = {
    "anthropic": ("Anthropic SDK", "anthropic"),
    "google": ("Google SDK", "google.genai"),
    "openai": ("OpenAI SDK", "openai"),
}


def _check_provider(provider: str) -> tuple[CheckResult, CheckResult]:
    """Return (sdk_result, key_result) for one cloud provider."""
    from parliament.config import KEY_PROVIDERS, api_key_status

    display_name, import_name = PROVIDER_DISPLAY[provider]

    # SDK check
    try:
        __import__(import_name)
        sdk_result = CheckResult(ok=True, message=display_name)
    except ImportError as e:
        sdk_result = CheckResult(ok=False, message=f"{display_name} not installed: {e}")

    # Key check
    env_var = KEY_PROVIDERS[provider]
    status = api_key_status(provider)
    if status == "configured":
        key_result = CheckResult(ok=True, message=f"{env_var} configured")
    else:
        key_result = CheckResult(ok=True, info=True, message=f"{env_var} not set")

    return sdk_result, key_result


def _check_ollama(base_url: str = "http://localhost:11434") -> CheckResult:
    """Probe the Ollama daemon. Unreachable is informational, not a failure."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return CheckResult(
                ok=True,
                message=f"Ollama: reachable, {len(models)} model(s) installed",
            )
        return CheckResult(
            ok=True,
            info=True,
            message=f"Ollama: unexpected status {response.status_code}",
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return CheckResult(
            ok=True,
            info=True,
            message=f"Ollama: not reachable at {base_url}",
        )


def _symbol_for(r: CheckResult) -> tuple[str, str]:
    """Map a CheckResult to (unicode-symbol, rich-color)."""
    if not r.ok:
        return ("✗", "red")        # ✗
    if r.warn:
        return ("!", "yellow")
    if r.info:
        return ("ℹ", "blue")       # ℹ
    return ("✓", "green")          # ✓


def run_doctor(console: Console) -> int:
    """Run all doctor checks and print a report. Returns exit code (0 ok, 1 broken)."""
    env_checks = [
        _check_python_version(),
        _check_curses(),
        _check_terminal_size(),
        _check_config(),
    ]

    console.print("[bold]Environment[/bold]")
    for r in env_checks:
        symbol, color = _symbol_for(r)
        console.print(f"  [{color}]{symbol}[/{color}] {r.message}")

    console.print("[bold]Providers[/bold]")
    provider_checks: list[CheckResult] = []
    for provider in ("anthropic", "google", "openai"):
        sdk_r, key_r = _check_provider(provider)
        provider_checks.extend([sdk_r, key_r])
        sdk_sym, sdk_col = _symbol_for(sdk_r)
        key_sym, key_col = _symbol_for(key_r)
        console.print(
            f"  [{sdk_col}]{sdk_sym}[/{sdk_col}] {sdk_r.message:<20} "
            f"[{key_col}]{key_sym}[/{key_col}] {key_r.message}"
        )

    ollama_result = _check_ollama()
    sym, col = _symbol_for(ollama_result)
    console.print(f"  [{col}]{sym}[/{col}] {ollama_result.message}")

    console.print("[bold]Next steps[/bold]")
    cloud_keys_missing = any(r.info for r in provider_checks)
    if cloud_keys_missing:
        console.print("  - Add cloud keys:   parliament keys set <provider> <key>")
    if ollama_result.info:
        console.print(
            "  - Local models?     Install Ollama from https://ollama.com, "
            "then `ollama pull llama3.1`"
        )
    console.print("  - Run the TUI:      parliament")

    all_checks = env_checks + provider_checks + [ollama_result]
    has_failure = any((not r.ok) for r in all_checks)
    if has_failure:
        console.print()
        console.print(
            "[red]Install is not functional. "
            "Fix the items marked with the failure symbol above.[/red]"
        )
        return 1
    return 0
