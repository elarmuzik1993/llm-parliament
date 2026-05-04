"""Health-check logic for `parliament doctor`."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

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

    console.print("[bold]Next steps[/bold]")

    all_checks = env_checks + provider_checks
    has_failure = any((not r.ok) for r in all_checks)
    return 1 if has_failure else 0
