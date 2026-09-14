"""OpenRouter provider wiring -- issue #36.

OpenRouter speaks the OpenAI API at its own address, so it needs no provider
class of its own: it is a row in `model_catalog.OPENAI_COMPATIBLE` plus one
line opting that row in as a wired provider, and the client, the key and the
doctor's key check all follow from there. These tests pin the row, the wiring,
the deliberate asymmetry with the discovery-only `groq`/`mistral` rows, and the
one property that must not regress -- that an OpenAI credential is never sent
to another vendor (#48).
"""

from __future__ import annotations

import pytest

from parliament.config import KEY_PROVIDERS, build_parliament_from_config
from parliament.model_catalog import OPENAI_COMPATIBLE
from parliament.providers import create_provider
from parliament.providers.openai_provider import OpenAIProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "anthropic/claude-sonnet-4-6"


@pytest.fixture(autouse=True)
def _no_ambient_keys(monkeypatch):
    """No inherited keys -- each test sets exactly what it means to test."""
    for env_var in KEY_PROVIDERS.values():
        monkeypatch.delenv(env_var, raising=False)


# ── The registry row ───────────────────────────────────────────────────────────


def test_openrouter_is_a_registry_row():
    spec = OPENAI_COMPATIBLE["openrouter"]

    assert spec.base_url == OPENROUTER_BASE_URL
    assert spec.env_var == "OPENROUTER_API_KEY"


def test_openrouter_key_is_registered_for_keys_set_and_the_doctor():
    assert KEY_PROVIDERS["openrouter"] == "OPENROUTER_API_KEY"


def test_every_wired_provider_has_a_home_for_its_key():
    """The invariant, structural rather than remembered.

    A name `create_provider` serves but `KEY_PROVIDERS` omits is one
    `parliament keys set` cannot reach and the doctor cannot report, so the two
    must agree. Checked against the wired list rather than every registry row:
    a row on its own is discovery-only (`groq`, `mistral`) and needs no key
    home, because no debate will ever read its variable.
    """
    from parliament.providers import _OPENAI_COMPATIBLE_PROVIDERS

    for name in _OPENAI_COMPATIBLE_PROVIDERS:
        spec = OPENAI_COMPATIBLE[name]
        assert KEY_PROVIDERS.get(name) == spec.env_var, (
            f"'{name}' is a wired provider but its key variable is missing "
            f"from KEY_PROVIDERS, so `parliament keys set {name}` cannot reach it."
        )


# ── Building a client ──────────────────────────────────────────────────────────


def test_openrouter_builds_an_openai_client_at_openrouters_address(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    provider = create_provider("openrouter", MODEL)

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == MODEL
    assert provider._base_url == OPENROUTER_BASE_URL
    assert provider._api_key == "sk-or-test"


def test_openrouter_does_not_borrow_the_openai_key(monkeypatch):
    """The #48 safety property, post-fix.

    `openai_compatible_key()` in `model_catalog` deliberately falls back to
    `OPENAI_API_KEY` for discovery, so the model picker can read Groq from the
    same variable someone uses to configure `provider: openai + base_url`. A
    missing `OPENROUTER_API_KEY` must not borrow that fallback to build the
    client: `AsyncOpenAI(api_key=None)` would silently resolve `OPENAI_API_KEY`
    itself and post a real OpenAI credential to OpenRouter. The fix is to raise
    rather than reach the SDK with `None`.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-real-openai-secret")

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_provider("openrouter", MODEL)


def test_openrouter_does_not_use_the_openai_key_when_both_are_set(monkeypatch):
    """The corollary: when the user does supply an `OPENROUTER_API_KEY`, the
    constructed client uses it -- not `OPENAI_API_KEY`. Reaching the SDK
    client (`_get_client().api_key`) proves no other layer swapped the
    credential, and is the assertion the previous form of this test stopped
    one call short of.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-real-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-dedicated")

    provider = create_provider("openrouter", MODEL)

    assert provider._api_key == "sk-or-dedicated"
    assert provider._get_client().api_key == "sk-or-dedicated"


def test_config_base_url_overrides_the_registry_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    provider = create_provider(
        "openrouter", MODEL, base_url="https://gateway.internal/v1"
    )

    assert provider._base_url == "https://gateway.internal/v1"


def test_config_api_key_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")

    provider = create_provider("openrouter", MODEL, api_key="sk-or-config")

    assert provider._api_key == "sk-or-config"


def test_groq_and_mistral_stay_discovery_only(monkeypatch):
    """Wiring a vendor is deliberate, not a side effect of having a row.

    #43 added the `groq` and `mistral` rows for the model picker, and the
    README still documents that `provider: groq` in a config is an error. Only
    `openrouter` is opted in by this change, so the other two must keep
    raising rather than quietly starting to work.
    """
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("groq", "llama-3.3-70b-versatile")


def test_openai_keeps_its_existing_behaviour(monkeypatch):
    """`provider: openai` must not be rerouted through the registry.

    An unset base_url means the SDK's own default, which is what the README's
    `base_url` recipe and the existing tests both rely on.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    provider = create_provider("openai", "gpt-4o")

    assert provider._base_url is None


def test_unknown_provider_still_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("zzz", "some-model")


# ── End to end from a config ───────────────────────────────────────────────────


def test_config_reaches_openrouter_end_to_end(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config = {
        "parliament": {
            "members": [{"name": "Claude", "provider": "openrouter", "model": MODEL}]
        },
        "providers": {"openrouter": {}},
    }

    members, providers = build_parliament_from_config(config)

    assert members[0].provider_name == "openrouter"
    assert providers["Claude"]._base_url == OPENROUTER_BASE_URL
    assert providers["Claude"]._api_key == "sk-or-test"


def test_config_can_override_the_base_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config = {
        "parliament": {
            "members": [{"name": "Claude", "provider": "openrouter", "model": MODEL}]
        },
        "providers": {"openrouter": {"base_url": "https://gateway.internal/v1"}},
    }

    _, providers = build_parliament_from_config(config)

    assert providers["Claude"]._base_url == "https://gateway.internal/v1"


# ── Key management surfaces ────────────────────────────────────────────────────


def test_keys_set_accepts_openrouter(monkeypatch, tmp_path):
    """`parliament keys set openrouter` must not be rejected by the CLI."""
    from click.testing import CliRunner

    import parliament.config as config_mod
    from parliament import cli

    monkeypatch.setattr(config_mod, "PARLIAMENT_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "KEYS_FILE", tmp_path / "keys.env")
    monkeypatch.setattr(config_mod, "_keyring_set", lambda env_var, value: False)
    monkeypatch.setattr(cli, "KEYS_FILE", tmp_path / "keys.env")

    result = CliRunner().invoke(cli.main, ["keys", "set", "openrouter", "sk-or-test"])

    assert result.exit_code == 0, result.output
    assert "OPENROUTER_API_KEY" in result.output
    assert "OPENROUTER_API_KEY=sk-or-test" in (tmp_path / "keys.env").read_text()


def test_key_command_offers_openrouter():
    from parliament.commands import CLOUD_KEY_PROVIDERS

    assert "openrouter" in CLOUD_KEY_PROVIDERS
