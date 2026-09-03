"""Tests for the PTU Advisor command-line interface."""

from typer.testing import CliRunner

from ptu_advisor.cli import app


def test_version_flag_reports_package_release_without_command() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "PTU Advisor v1.1.0" in result.stdout