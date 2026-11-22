"""Tests for the ``lakehouse sample`` and ``lakehouse doctor`` commands."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.unit.cli_support import plain
from typer.testing import CliRunner

from ecuador_lakehouse.cli.app import app
from ecuador_lakehouse.domain.errors import ChecksumMismatchError
from ecuador_lakehouse.domain.sample import ControlTotal, SampleBuildReport, SampleFile
from ecuador_lakehouse.domain.sources import SourceId

runner = CliRunner()


def test_root_help_lists_the_sample_and_doctor_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "sample" in result.output
    assert "doctor" in result.output


def test_sample_build_help_lists_the_maintainer_options() -> None:
    result = runner.invoke(app, ["sample", "build", "--help"])

    output = plain(result.stdout)
    assert result.exit_code == 0
    for option in ("--years", "--cache-dir", "--output-dir", "--seed-dir"):
        assert option in output


def test_sample_build_rejects_invalid_years_with_exit_two() -> None:
    result = runner.invoke(app, ["sample", "build", "--years", "2019-bogus"])

    assert result.exit_code == 2
    assert "invalid --years" in result.output
    assert "Traceback" not in result.output


def test_doctor_reports_a_checksum_failure_with_exit_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_settings: object) -> int:
        raise ChecksumMismatchError("checksum mismatch for bundled sample")

    monkeypatch.setattr("ecuador_lakehouse.cli.commands.doctor.verify_sample_integrity", fail)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 3
    assert "checksum mismatch" in result.output
    assert "Traceback" not in result.output


def test_sample_build_prints_the_report(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = SampleFile(
        name="sri_tax_collection_2019.csv.gz",
        source_id=SourceId.SRI_TAX,
        partition="2019",
        size_bytes=223_491,
        sha256="a" * 64,
        rows=24_035,
        derived_from_sha256="b" * 64,
    )
    total = ControlTotal(SourceId.SRI_TAX, 2019, Decimal("14268758446.78"), True, "2026-11-19")
    report = SampleBuildReport(
        files=(entry,),
        control_totals=(total,),
        cached=("sri_tax_collection_2019.csv.gz",),
    )
    calls: list[tuple[int, ...]] = []

    class FakeFetcher:
        def close(self) -> None:
            pass

    class FakeBuilder:
        fetcher = FakeFetcher()

        def execute(self, years: object) -> SampleBuildReport:
            calls.append(tuple(years))  # type: ignore[arg-type]
            return report

    monkeypatch.setattr(
        "ecuador_lakehouse.cli.commands.sample.build_sample_builder",
        lambda *_args, **_kwargs: FakeBuilder(),
    )

    result = runner.invoke(app, ["sample", "build", "--years", "2019"])

    assert result.exit_code == 0
    assert calls == [(2019,)]
    assert "sha256 OK aaaaaaaa sri_tax_collection_2019.csv.gz" in result.output
    assert "(223491 bytes, cached, 24035 rows)" in result.output
    assert "Wrote 1 sample files (223491 bytes)." in result.output
    assert "Control totals: 1 SRI rows." in result.output
