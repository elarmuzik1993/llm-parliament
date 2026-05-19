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


def _format_gb(size_bytes: int) -> str:
    return f"{size_bytes / 1024**3:.1f} GB"


def _system_ram_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.virtual_memory().total)


def _check_member_viability(config: dict | None = None) -> list[CheckResult]:
    """Check configured members against provider keys, Ollama installs, and RAM."""
    from parliament.config import KEY_PROVIDERS, api_key_status, load_config
    from parliament.model_catalog import _ollama_base_url, fetch_ollama_models

    cfg = config if config is not None else load_config()
    members = (cfg.get("parliament") or {}).get("members") or []
    results: list[CheckResult] = []
    installed_local_sizes: list[int] = []
    ollama_members = [
        m for m in members
        if isinstance(m, dict) and str(m.get("provider") or "") == "ollama"
    ]
    base_url = _ollama_base_url(cfg)
    ollama_sizes: dict[str, int] = {}
    if ollama_members:
        ollama_data = fetch_ollama_models(base_url)
        ollama_sizes = {m.name: m.size_bytes for m in ollama_data.ollama_models}

    for member in members:
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or "Member")
        provider = str(member.get("provider") or "")
        model = str(member.get("model") or "")

        if provider == "mock":
            continue
        if provider in KEY_PROVIDERS:
            env_var = KEY_PROVIDERS[provider]
            if api_key_status(provider) == "configured":
                results.append(
                    CheckResult(
                        ok=True,
                        message=f"{name} ({provider} / {model}) - key configured",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        ok=True,
                        warn=True,
                        message=f"{name} member needs {env_var}",
                    )
                )
            continue
        if provider == "ollama":
            if model not in ollama_sizes:
                results.append(
                    CheckResult(
                        ok=True,
                        warn=True,
                        message=f"{name} (ollama / {model}) - not pulled. "
                        f"Run: ollama pull {model}",
                    )
                )
                continue
            size = ollama_sizes[model]
            installed_local_sizes.append(size)
            results.append(
                CheckResult(
                    ok=True,
                    message=f"{name} (ollama / {model}) - installed, {_format_gb(size)}",
                )
            )

    if ollama_members:
        total_ram = _system_ram_bytes()
        if total_ram is None:
            results.append(
                CheckResult(
                    ok=True,
                    info=True,
                    message="RAM check skipped (psutil not installed)",
                )
            )
        elif installed_local_sizes:
            total = sum(installed_local_sizes)
            limit = int(total_ram * 0.8)
            if total > limit:
                results.append(
                    CheckResult(
                        ok=True,
                        warn=True,
                        message=(
                            f"Members may OOM: ~{_format_gb(total)} needed for local "
                            f"models, {_format_gb(total_ram)} RAM "
                            f"(limit {_format_gb(limit)} at 80%)"
                        ),
                    )
                )
            else:
                results.append(
                    CheckResult(
                        ok=True,
                        message=(
                            f"Aggregate footprint: ~{_format_gb(total)} / "
                            f"{_format_gb(total_ram)} RAM (well within limit)"
                        ),
                    )
                )

    return results


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

    member_checks = _check_member_viability()
    if member_checks:
        console.print("[bold]Members[/bold]")
        for r in member_checks:
            symbol, color = _symbol_for(r)
            console.print(f"  [{color}]{symbol}[/{color}] {r.message}")

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

    all_checks = env_checks + provider_checks + [ollama_result] + member_checks
    has_failure = any((not r.ok) for r in all_checks)
    if has_failure:
        console.print()
        console.print(
            "[red]Install is not functional. "
            "Fix the items marked with the failure symbol above.[/red]"
        )
        return 1
    return 0
