"""Named OpenAI-compatible providers use only their own credentials (#48)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from parliament import cli, config, model_catalog
from parliament.commands import CLOUD_KEY_PROVIDERS
from parliament.providers import create_provider
from parliament.tui import SUPPORTED_PROVIDERS


@pytest.fixture(params=["openrouter", "groq", "mistral"])
def vendor(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    for spec in model_catalog.OPENAI_COMPATIBLE.values():
        monkeypatch.delenv(spec.env_var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-only-test-key")
    return request.param


def test_named_provider_uses_dedicated_key(vendor: str, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = model_catalog.OPENAI_COMPATIBLE[vendor]
    monkeypatch.setenv(spec.env_var, "vendor-test-key")
    provider = create_provider(vendor, "test-model")
    assert provider._base_url == spec.base_url
    assert provider._get_client().api_key == "vendor-test-key"
    assert model_catalog.openai_compatible_key(vendor) == "vendor-test-key"


def test_missing_vendor_key_cannot_borrow_openai_key(vendor: str) -> None:
    spec = model_catalog.OPENAI_COMPATIBLE[vendor]
    assert model_catalog.openai_compatible_key(vendor) is None
    with pytest.raises(ValueError, match=spec.env_var):
        create_provider(vendor, "test-model")


def test_config_wires_vendor_and_overrides(vendor: str) -> None:
    settings = {
        "parliament": {"members": [{"name": "Member", "provider": vendor, "model": "model"}]},
        "providers": {vendor: {"api_key": "config-test-key", "base_url": "https://example.test/v1"}},
    }
    members, providers = config.build_parliament_from_config(settings)
    assert members[0].provider_name == vendor
    assert providers["Member"]._base_url == "https://example.test/v1"
    assert providers["Member"]._get_client().api_key == "config-test-key"


def test_keys_set_and_picker_support_vendor(
    vendor: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    spec = model_catalog.OPENAI_COMPATIBLE[vendor]
    assert vendor in SUPPORTED_PROVIDERS
    assert vendor in CLOUD_KEY_PROVIDERS
    assert config.KEY_PROVIDERS[vendor] == spec.env_var
    monkeypatch.setattr(config, "PARLIAMENT_DIR", tmp_path)
    monkeypatch.setattr(config, "KEYS_FILE", tmp_path / "keys.env")
    monkeypatch.setattr(config, "_keyring_set", lambda env_var, value: False)
    monkeypatch.setattr(cli, "KEYS_FILE", tmp_path / "keys.env")
    result = CliRunner().invoke(cli.main, ["keys", "set", vendor, "vendor-test-key"])
    assert result.exit_code == 0, result.output
    assert f"{spec.env_var}=vendor-test-key" in (tmp_path / "keys.env").read_text()
