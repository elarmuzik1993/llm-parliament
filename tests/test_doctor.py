"""Health-check command tests."""

from __future__ import annotations

from click.testing import CliRunner


def test_doctor_command_runs_and_exits_zero_on_a_working_install(monkeypatch, tmp_path):
    """Bare smoke test: `parliament doctor` runs without crashing on a healthy box."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from parliament import cli

    result = CliRunner().invoke(cli.main, ["doctor"])

    # Skeleton phase: the command exists and exits 0 when there's nothing wrong.
    assert result.exit_code == 0, result.output
    assert "Environment" in result.output or "Doctor" in result.output
