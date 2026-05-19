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
KEYRING_SERVICE = "llm-parliament"

KEY_PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def _keyring_get(env_var: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, env_var)
    except Exception:
        return None


def _keyring_set(env_var: str, value: str) -> bool:
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, env_var, value)
        return keyring.get_password(KEYRING_SERVICE, env_var) == value
    except Exception:
        return False


def _keyring_delete(env_var: str) -> bool:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, env_var)
        return True
    except Exception:
        return False


def get_keyring_key(env_var: str) -> str | None:
    """Return a key from the OS keyring, or None if not stored / keyring unavailable."""
    return _keyring_get(env_var)


def api_key_status(provider: str) -> str:
    """Return 'configured', 'missing', or 'not required' for a provider's API key."""
    env_var = KEY_PROVIDERS.get(provider)
    if env_var is None:
        return "not required"
    return "configured" if os.environ.get(env_var) else "missing"


_TRUTHY = {"1", "true", "yes", "on"}


def resolve_show_debate(*, cli_flag: bool | None, config: dict[str, Any]) -> bool:
    """Decide whether to render the debate live.

    Precedence: CLI flag > PARLIAMENT_SHOW_DEBATE env var > config display.show_debate
    > default True.
    """
    if cli_flag is not None:
        return bool(cli_flag)
    env = os.environ.get("PARLIAMENT_SHOW_DEBATE")
    if env is not None:
        return env.strip().lower() in _TRUTHY
    display = config.get("display") or {}
    if "show_debate" in display:
        return bool(display["show_debate"])
    return True


def resolve_hansard_level(*, cli_flag: str | None, config: dict[str, Any]):
    """Decide the Hansard detail level for this run.

    Precedence: CLI flag > PARLIAMENT_HANSARD_LEVEL env var > config
    `hansard.level` > default `minimal`. Unknown values normalise to
    `minimal` via `HansardLevel.parse`.
    """
    # Local import to avoid circular dependency: parliament.render.hansard
    # imports from parliament.core.types (which is fine), but we keep
    # config.py free of render package imports at module-load time.
    from parliament.render.hansard import HansardLevel

    if cli_flag is not None:
        return HansardLevel.parse(cli_flag)
    env = os.environ.get("PARLIAMENT_HANSARD_LEVEL")
    if env is not None:
        return HansardLevel.parse(env)
    raw = (config.get("hansard") or {}).get("level")
    return HansardLevel.parse(raw)


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
    """Load API keys from ~/.parliament/keys.env and OS keyring."""
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
    for env_var in KEY_PROVIDERS.values():
        if env_var not in keys:
            val = _keyring_get(env_var)
            if val:
                os.environ.setdefault(env_var, val)
                keys[env_var] = val
    return keys


def save_key(provider: str, key: str) -> str:
    """Save an API key. Prefers OS keyring; falls back to keys.env.

    Returns 'keyring' or 'file' indicating where the key was stored.
    """
    PARLIAMENT_DIR.mkdir(parents=True, exist_ok=True)
    env_var = f"{provider.upper()}_API_KEY"
    os.environ[env_var] = key

    if _keyring_set(env_var, key):
        return "keyring"

    # Keyring unavailable — fall back to file storage
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
    if sys.platform != "win32":
        KEYS_FILE.chmod(0o600)
    return "file"


def remove_key(provider: str) -> bool:
    """Remove an API key from keys.env and OS keyring. Returns True if key existed."""
    env_var = f"{provider.upper()}_API_KEY"
    found = False

    if KEYS_FILE.exists():
        lines = []
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(env_var + "="):
                found = True
            else:
                lines.append(line)
        if found:
            KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if _keyring_delete(env_var):
        found = True

    return found


def migrate_keys_to_keyring() -> dict[str, str]:
    """Migrate API keys from keys.env to the OS keyring.

    Returns {env_var: 'migrated'|'failed'}.
    Renames keys.env → keys.env.bak on full success.
    """
    if not KEYS_FILE.exists():
        return {}

    file_keys: dict[str, str] = {}
    for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            file_keys[k.strip()] = v.strip()

    if not file_keys:
        return {}

    results: dict[str, str] = {}
    for env_var, value in file_keys.items():
        results[env_var] = "migrated" if _keyring_set(env_var, value) else "failed"

    if all(s == "migrated" for s in results.values()):
        KEYS_FILE.rename(KEYS_FILE.parent / "keys.env.bak")

    return results


def _ensure_user_config() -> Path:
    """Create ~/.parliament/config.yaml on first run."""
    if not USER_CONFIG.exists():
        if not EXAMPLE_CONFIG.exists():
            raise FileNotFoundError(
                f"Example config missing: {EXAMPLE_CONFIG}. Reinstall the package."
            )
        PARLIAMENT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            from parliament.first_run import run_first_run_wizard

            run_first_run_wizard(USER_CONFIG)
        except Exception as e:
            shutil.copyfile(EXAMPLE_CONFIG, USER_CONFIG)
            print(
                f"First-run wizard failed ({type(e).__name__}: {e}); "
                f"created default config at {USER_CONFIG}.",
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
