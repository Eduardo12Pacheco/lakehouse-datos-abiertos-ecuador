"""Tests for the package version and the ``--version`` CLI flag."""

from __future__ import annotations

import runpy
import sys
import warnings

import pytest
from tests.unit.project_info import project_version
from typer.testing import CliRunner

from ecuador_lakehouse import __version__
from ecuador_lakehouse.cli.app import _print_version, app


def test_package_exposes_version() -> None:
    assert __version__ == project_version()


def test_cli_version_flag_prints_version_and_exits_zero() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == project_version()


def test_version_callback_is_a_noop_without_the_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loads: list[str] = []
    monkeypatch.setattr(
        "ecuador_lakehouse.cli.app._load_settings",
        lambda: loads.append("loaded"),
    )

    assert _print_version(False) is None
    assert capsys.readouterr().out == ""
    assert loads == []


def test_python_dash_m_prints_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["lakehouse", "--version"])

    with warnings.catch_warnings():
        # runpy warns because the parent package was already imported by the suite.
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("ecuador_lakehouse", run_name="__main__")

    assert excinfo.value.code == 0
