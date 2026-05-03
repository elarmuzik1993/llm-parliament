"""Config loading — YAML parsing, env var resolution, key management."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from parliament.core.types import Member
from parliament.core.model_tiers import get_tier
from parliament.providers import create_provider
from parliament.providers.base import Provider

PARLIAMENT_DIR = Path.home() / ".parliament"
KEYS_FILE = PARLIAMENT_DIR / "keys.env"
USER_CONFIG = PARLIAMENT_DIR / "config.yaml"
EXAMPLE_CONFIG = Path(__file__).parent.parent.parent / "config.example.yaml"


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} with environment variable values."""
    def replacer(match):
        var = match.group(1)
        val = os.environ.get(var)
        if val is None:
            raise ValueError(f"Environment variable ${{{var}}} not set")
        return val
    return re.sub(r"\$\{(\w+)\}", replacer, value)


def load_keys() -> dict[str, str]:
    """Load API keys from ~/.parliament/keys.env."""
    keys = {}
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
                keys[key.strip()] = value.strip()
    return keys


def save_key(provider: str, key: str) -> None:
    """Save an API key to ~/.parliament/keys.env."""
    PARLIAMENT_DIR.mkdir(parents=True, exist_ok=True)

    env_var = f"{provider.upper()}_API_KEY"
    lines = []
    replaced = False

    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(env_var + "="):
                lines.append(f"{env_var}={key}")
                replaced = True
            else:
                lines.append(line)

    if not replaced:
        lines.append(f"{env_var}={key}")

    KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Restrict permissions on Unix; Windows ACLs don't support chmod
    if sys.platform != "win32":
        KEYS_FILE.chmod(0o600)


def remove_key(provider: str) -> bool:
    """Remove an API key. Returns True if key existed."""
    if not KEYS_FILE.exists():
        return False

    env_var = f"{provider.upper()}_API_KEY"
    lines = []
    found = False

    for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(env_var + "="):
            found = True
        else:
            lines.append(line)

    if found:
        KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


def _ensure_user_config() -> Path:
    """Create ~/.parliament/config.yaml from the bundled example on first run."""
    if not USER_CONFIG.exists():
        if not EXAMPLE_CONFIG.exists():
            raise FileNotFoundError(
                f"Example config missing: {EXAMPLE_CONFIG}. Reinstall the package."
            )
        PARLIAMENT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXAMPLE_CONFIG, USER_CONFIG)
        print(
            f"Created default config at {USER_CONFIG} — "
            f"edit it via `parliament members` or the TUI.",
            file=sys.stderr,
        )
    return USER_CONFIG


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and resolve a parliament config file."""
    load_keys()  # inject keys.env into env before resolving

    path = config_path or _ensure_user_config()
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = path.read_text(encoding="utf-8")
    # Resolve env vars in the raw YAML
    try:
        resolved = _resolve_env_vars(raw)
    except ValueError:
        # If env vars can't resolve, load raw and let provider init fail with clear message
        resolved = raw

    return yaml.safe_load(resolved)


def save_config(config: dict[str, Any], config_path: Path) -> None:
    """Atomically save a parliament config file."""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    payload = yaml.safe_dump(config, sort_keys=False, default_flow_style=False)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(config_path.parent),
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        if not payload.endswith("\n"):
            tmp.write("\n")
        tmp_path = Path(tmp.name)

    tmp_path.replace(config_path)


def build_parliament_from_config(
    config: dict[str, Any],
) -> tuple[list[Member], dict[str, Provider]]:
    """Parse config dict into Members and Providers ready for Parliament."""
    members = []
    providers = {}

    provider_configs = config.get("providers", {})

    for mc in config["parliament"]["members"]:
        name = mc["name"]
        provider_name = mc["provider"]
        model = mc["model"]
        tier = get_tier(model)

        member = Member(name=name, provider_name=provider_name, model=model, tier=tier)
        members.append(member)

        # Build provider with any extra config (base_url, api_key, etc.)
        extra = {}
        if provider_name in provider_configs:
            extra = {k: v for k, v in provider_configs[provider_name].items()}

        providers[name] = create_provider(provider_name, model, **extra)

    return members, providers
