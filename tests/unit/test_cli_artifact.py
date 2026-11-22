"""Unit tests for the artifact CLI surface (S1, S14)."""

from __future__ import annotations

from tests.unit.cli_support import plain
from typer.testing import CliRunner

from ecuador_lakehouse.cli.app import app

runner = CliRunner()


def test_root_help_lists_the_artifact_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("build", "test", "fetch", "sample", "publish", "verify", "docs", "doctor"):
        assert command in result.output
    assert "contract" in result.output


def test_contract_group_lists_the_check_command() -> None:
    result = runner.invoke(app, ["contract", "--help"])

    assert result.exit_code == 0
    assert "check" in result.output


def test_publish_and_verify_help_describe_their_arguments() -> None:
    publish = runner.invoke(app, ["publish", "--help"])
    verify = runner.invoke(app, ["verify", "--help"])

    assert publish.exit_code == 0
    assert "--out" in plain(publish.output)
    assert verify.exit_code == 0
    assert "ARTIFACT_DIR" in plain(verify.output).upper()


def test_verify_without_an_artifact_exits_eight(tmp_path) -> None:
    result = runner.invoke(app, ["verify", str(tmp_path / "missing")])

    assert result.exit_code == 8
    assert "does not exist" in result.output
