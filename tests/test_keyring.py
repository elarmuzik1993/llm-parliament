"""Tests for OS keyring integration (USE-31)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from parliament import cli
from parliament.config import (
    KEYRING_SERVICE,
    get_keyring_key,
    load_keys,
    migrate_keys_to_keyring,
    remove_key,
    save_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_keyring_mock(stored: dict[str, str] | None = None) -> MagicMock:
    """Return a mock keyring module backed by an in-memory dict.

    Matches real keyring behavior: delete_password raises when key absent.
    """
    store: dict[str, str] = dict(stored or {})

    def fake_delete(svc: str, key: str) -> None:
        if key not in store:
            raise RuntimeError(f"PasswordDeleteError: {key} not found")
        store.pop(key)

    kr = MagicMock()
    kr.get_password.side_effect = lambda svc, key: store.get(key)
    kr.set_password.side_effect = lambda svc, key, val: store.update({key: val})
    kr.delete_password.side_effect = fake_delete
    return kr


def _make_broken_keyring() -> MagicMock:
    """Return a mock keyring that raises on every call."""
    kr = MagicMock()
    kr.get_password.side_effect = RuntimeError("no keyring daemon")
    kr.set_password.side_effect = RuntimeError("no keyring daemon")
    kr.delete_password.side_effect = RuntimeError("no keyring daemon")
    return kr


# ---------------------------------------------------------------------------
# _keyring_get / get_keyring_key
# ---------------------------------------------------------------------------

def test_get_keyring_key_returns_stored_value():
    kr = _make_keyring_mock({"ANTHROPIC_API_KEY": "sk-ant-test"})
    with patch.dict("sys.modules", {"keyring": kr}):
        val = get_keyring_key("ANTHROPIC_API_KEY")
    assert val == "sk-ant-test"


def test_get_keyring_key_returns_none_when_not_set():
    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        val = get_keyring_key("ANTHROPIC_API_KEY")
    assert val is None


def test_get_keyring_key_returns_none_on_exception():
    kr = _make_broken_keyring()
    with patch.dict("sys.modules", {"keyring": kr}):
        val = get_keyring_key("ANTHROPIC_API_KEY")
    assert val is None


# ---------------------------------------------------------------------------
# save_key
# ---------------------------------------------------------------------------

def test_save_key_uses_keyring_when_available(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        result = save_key("anthropic", "sk-ant-live")
    assert result == "keyring"
    kr.set_password.assert_called_once_with(KEYRING_SERVICE, "ANTHROPIC_API_KEY", "sk-ant-live")


def test_save_key_falls_back_to_file_when_keyring_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "PARLIAMENT_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_broken_keyring()
    with patch.dict("sys.modules", {"keyring": kr}):
        result = save_key("anthropic", "sk-ant-live")

    assert result == "file"
    assert (tmp_path / "keys.env").exists()
    assert "ANTHROPIC_API_KEY=sk-ant-live" in (tmp_path / "keys.env").read_text()


def test_save_key_sets_env_var(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        save_key("openai", "sk-openai-test")
    import os
    assert os.environ.get("OPENAI_API_KEY") == "sk-openai-test"


# ---------------------------------------------------------------------------
# load_keys — keyring fallback
# ---------------------------------------------------------------------------

def test_load_keys_falls_back_to_keyring_when_file_missing(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    kr = _make_keyring_mock({"GOOGLE_API_KEY": "AIza-test"})
    with patch.dict("sys.modules", {"keyring": kr}):
        keys = load_keys()

    assert keys.get("GOOGLE_API_KEY") == "AIza-test"


def test_load_keys_file_takes_precedence_over_keyring(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", keys_file)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    kr = _make_keyring_mock({"OPENAI_API_KEY": "sk-from-keyring"})
    with patch.dict("sys.modules", {"keyring": kr}):
        keys = load_keys()

    assert keys.get("OPENAI_API_KEY") == "sk-from-file"


def test_load_keys_graceful_when_keyring_broken(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_broken_keyring()
    with patch.dict("sys.modules", {"keyring": kr}):
        keys = load_keys()

    assert isinstance(keys, dict)


# ---------------------------------------------------------------------------
# remove_key
# ---------------------------------------------------------------------------

def test_remove_key_clears_keyring(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_keyring_mock({"ANTHROPIC_API_KEY": "sk-ant-test"})
    with patch.dict("sys.modules", {"keyring": kr}):
        found = remove_key("anthropic")

    assert found is True
    kr.delete_password.assert_called_once_with(KEYRING_SERVICE, "ANTHROPIC_API_KEY")


def test_remove_key_returns_true_when_only_in_keyring(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_keyring_mock({"ANTHROPIC_API_KEY": "sk-ant-test"})
    with patch.dict("sys.modules", {"keyring": kr}):
        found = remove_key("anthropic")

    assert found is True


def test_remove_key_returns_false_when_nowhere(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        found = remove_key("anthropic")

    assert found is False


# ---------------------------------------------------------------------------
# migrate_keys_to_keyring
# ---------------------------------------------------------------------------

def test_migrate_moves_file_keys_to_keyring(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\nOPENAI_API_KEY=sk-oai-test\n")
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", keys_file)

    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        results = migrate_keys_to_keyring()

    assert results == {"ANTHROPIC_API_KEY": "migrated", "OPENAI_API_KEY": "migrated"}


def test_migrate_renames_file_to_bak_on_success(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", keys_file)

    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        migrate_keys_to_keyring()

    assert not keys_file.exists()
    assert (tmp_path / "keys.env.bak").exists()


def test_migrate_preserves_file_on_partial_failure(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", keys_file)

    kr = _make_broken_keyring()
    with patch.dict("sys.modules", {"keyring": kr}):
        results = migrate_keys_to_keyring()

    assert results == {"ANTHROPIC_API_KEY": "failed"}
    assert keys_file.exists()


def test_migrate_returns_empty_when_no_file(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", tmp_path / "keys.env")

    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        results = migrate_keys_to_keyring()

    assert results == {}


def test_migrate_returns_empty_when_file_has_no_keys(monkeypatch, tmp_path):
    import parliament.config as cfg_mod
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("# just a comment\n\n")
    monkeypatch.setattr(cfg_mod, "KEYS_FILE", keys_file)

    kr = _make_keyring_mock()
    with patch.dict("sys.modules", {"keyring": kr}):
        results = migrate_keys_to_keyring()

    assert results == {}


# ---------------------------------------------------------------------------
# CLI: keys migrate subcommand
# ---------------------------------------------------------------------------

def test_cli_keys_migrate_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "KEYS_FILE", tmp_path / "keys.env")

    result = CliRunner().invoke(cli.main, ["keys", "migrate"])

    assert result.exit_code == 0
    assert "nothing to migrate" in result.output.lower()


def test_cli_keys_migrate_success(monkeypatch, tmp_path):
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
    monkeypatch.setattr(cli, "KEYS_FILE", keys_file)

    def fake_migrate():
        return {"ANTHROPIC_API_KEY": "migrated"}

    monkeypatch.setattr(cli, "migrate_keys_to_keyring", fake_migrate)

    result = CliRunner().invoke(cli.main, ["keys", "migrate"])

    assert result.exit_code == 0
    assert "ANTHROPIC_API_KEY" in result.output
    assert "Migration complete" in result.output


def test_cli_keys_migrate_failure(monkeypatch, tmp_path):
    keys_file = tmp_path / "keys.env"
    keys_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
    monkeypatch.setattr(cli, "KEYS_FILE", keys_file)

    def fake_migrate():
        return {"ANTHROPIC_API_KEY": "failed"}

    monkeypatch.setattr(cli, "migrate_keys_to_keyring", fake_migrate)

    result = CliRunner().invoke(cli.main, ["keys", "migrate"])

    assert result.exit_code == 0
    assert "could not be migrated" in result.output.lower()


# ---------------------------------------------------------------------------
# CLI: keys list shows keyring source
# ---------------------------------------------------------------------------

def test_cli_keys_list_shows_keyring_source(monkeypatch):
    secret = "sk-ant-keyring-abc123"
    monkeypatch.setattr(cli, "load_keys", lambda: {"ANTHROPIC_API_KEY": secret})
    monkeypatch.setattr(cli, "get_keyring_key", lambda env_var: secret if env_var == "ANTHROPIC_API_KEY" else None)
    for env_var in cli.KEY_PROVIDERS.values():
        monkeypatch.delenv(env_var, raising=False)

    result = CliRunner().invoke(cli.main, ["keys", "list"])

    assert result.exit_code == 0
    assert "keyring" in result.output
    assert "anthropic" in result.output


# ---------------------------------------------------------------------------
# CLI: keys set reports storage location
# ---------------------------------------------------------------------------

def test_cli_keys_set_reports_keyring(monkeypatch):
    monkeypatch.setattr(cli, "save_key", lambda provider, key: "keyring")

    result = CliRunner().invoke(cli.main, ["keys", "set", "anthropic", "sk-ant-test"])

    assert result.exit_code == 0
    assert "OS keyring" in result.output


def test_cli_keys_set_reports_file(monkeypatch):
    monkeypatch.setattr(cli, "save_key", lambda provider, key: "file")

    result = CliRunner().invoke(cli.main, ["keys", "set", "anthropic", "sk-ant-test"])

    assert result.exit_code == 0
    assert "keys.env" in result.output or str(cli.KEYS_FILE) in result.output
