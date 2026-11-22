"""Tests for the ``build``/``test`` commands, presenters and the CLI error boundary."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.unit.cli_support import plain
from typer.testing import CliRunner

from ecuador_lakehouse.application.pipeline import RunReport
from ecuador_lakehouse.cli.app import app
from ecuador_lakehouse.cli.presenters import quality_line, run_table
from ecuador_lakehouse.domain.errors import ConfigError, QualityGateError
from ecuador_lakehouse.domain.runs import RunRecord, RunStatus, StepResult, StepStatus

runner = CliRunner()


def _report(*, passed: int = 264) -> RunReport:
    timestamp = datetime(2026, 11, 20, 9, 0, 0, tzinfo=UTC).replace(tzinfo=None)
    steps = (
        StepResult("acquire", StepStatus.OK, 0.1, "12 partitions acquired", {"fetched": 12}),
        StepResult(
            "load_raw",
            StepStatus.OK,
            2.0,
            "12 loaded, 0 skipped, 0 replaced",
            {"loaded": 12, "skipped": 0, "replaced": 0},
        ),
        StepResult("transform", StepStatus.OK, 9.0, "dbt seed + run completed"),
        StepResult(
            "quality",
            StepStatus.OK,
            14.0,
            f"{passed}/264 tests passed",
            {"tests_total": 264, "tests_passed": passed},
        ),
        StepResult("docs", StepStatus.OK, 3.0, "static docs at index.html"),
        StepResult("report", StepStatus.OK, 0.1, "12 batches described", {"batches": 12}),
    )
    return RunReport(
        record=RunRecord(
            run_id="run-test",
            started_at=timestamp,
            finished_at=timestamp,
            status=RunStatus.OK,
            mode="sample",
            steps=steps,
        )
    )


class FakePipeline:
    def __init__(self, *, report: RunReport | None = None, error: Exception | None = None) -> None:
        self.report = report if report is not None else _report()
        self.error = error
        self.kwargs: dict[str, object] = {}

    def run(self, **kwargs: object) -> RunReport:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.report


class FakeContainer:
    def __init__(self, pipeline: FakePipeline) -> None:
        self.pipeline = pipeline
        self.closed = False

    def close(self) -> None:
        self.closed = True


def patch_container(
    monkeypatch: pytest.MonkeyPatch,
    container: FakeContainer,
    module: str,
    captured: dict[str, object] | None = None,
) -> None:
    def fake(_settings: object, **kwargs: object) -> FakeContainer:
        if captured is not None:
            captured.update(kwargs)
        return container

    monkeypatch.setattr(f"ecuador_lakehouse.cli.commands.{module}.build_container", fake)


def test_build_prints_every_step_and_closes_the_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline()
    container = FakeContainer(pipeline)
    patch_container(monkeypatch, container, "build")

    result = runner.invoke(app, ["build"])

    assert result.exit_code == 0
    assert container.closed is True
    for step in ("acquire", "load_raw", "transform", "quality", "docs", "report"):
        assert step in result.output
    assert "12 loaded" in result.output
    assert pipeline.kwargs == {"select": None, "only": None, "from_step": None}


def test_build_forwards_selection_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline()
    patch_container(monkeypatch, FakeContainer(pipeline), "build")

    result = runner.invoke(app, ["build", "--select", "report"])

    assert result.exit_code == 0
    assert pipeline.kwargs["select"] == ["report"]


def test_build_forwards_only_and_from_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    for flag, value in (("--only", "quality"), ("--from-step", "docs")):
        pipeline = FakePipeline()
        patch_container(monkeypatch, FakeContainer(pipeline), "build")

        result = runner.invoke(app, ["build", flag, value])

        assert result.exit_code == 0
        assert pipeline.kwargs[flag.removeprefix("--").replace("-", "_")] == value


def test_build_maps_a_closed_quality_gate_to_exit_seven(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline(error=QualityGateError("quality gate failed: bad_test"))
    container = FakeContainer(pipeline)
    patch_container(monkeypatch, container, "build")

    result = runner.invoke(app, ["build"])

    assert result.exit_code == 7
    assert "quality gate failed" in result.output
    assert "Traceback" not in result.output
    assert container.closed is True


def test_build_rejects_unknown_selection_with_exit_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))

    result = runner.invoke(app, ["build", "--select", "bogus"])

    assert result.exit_code == 2
    assert "unknown step" in result.output
    assert "Traceback" not in result.output


def test_build_rejects_combined_selection_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))

    result = runner.invoke(app, ["build", "--select", "quality", "--only", "quality"])

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_unexpected_error_maps_to_exit_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline(error=RuntimeError("kaboom"))
    patch_container(monkeypatch, FakeContainer(pipeline), "build")

    result = runner.invoke(app, ["build"])

    assert result.exit_code == 1
    assert "Unexpected error: kaboom" in result.output
    assert result.exception is not None


def test_debug_flag_shows_the_traceback(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline(error=RuntimeError("kaboom"))
    patch_container(monkeypatch, FakeContainer(pipeline), "build")

    result = runner.invoke(app, ["--debug", "build"])

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)


def test_test_command_prints_the_quality_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline()
    container = FakeContainer(pipeline)
    patch_container(monkeypatch, container, "test")

    result = runner.invoke(app, ["test"])

    assert result.exit_code == 0
    assert "PASS 264/264" in result.output
    assert pipeline.kwargs == {"only": "quality"}
    assert container.closed is True


def test_test_command_maps_a_failing_gate_to_exit_seven(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    pipeline = FakePipeline(error=QualityGateError("1 test failed"))
    patch_container(monkeypatch, FakeContainer(pipeline), "test")

    result = runner.invoke(app, ["test"])

    assert result.exit_code == 7
    assert "Error: 1 test failed" in result.output


def test_help_lists_build_and_test_options() -> None:
    build_help = runner.invoke(app, ["build", "--help"])
    test_help = runner.invoke(app, ["test", "--help"])

    assert build_help.exit_code == 0
    for option in ("--select", "--only", "--from-step"):
        assert option in plain(build_help.output)
    assert test_help.exit_code == 0
    assert "quality" in plain(test_help.output).lower()


def test_run_table_renders_steps_and_status() -> None:
    table = run_table(_report())

    assert [column.header for column in table.columns] == ["Step", "Status", "Duration", "Detail"]
    assert table.row_count == 6


def test_quality_line_reports_pass_and_fail() -> None:
    assert quality_line(_report()) == "PASS 264/264 dbt data and unit tests"
    assert quality_line(_report(passed=200)) == "FAIL 200/264 dbt data and unit tests"


def test_quality_line_without_quality_step_is_a_config_error() -> None:
    timestamp = datetime(2026, 11, 20, tzinfo=UTC).replace(tzinfo=None)
    report = RunReport(
        record=RunRecord(
            run_id="run",
            started_at=timestamp,
            finished_at=timestamp,
            status=RunStatus.OK,
            mode="sample",
        )
    )

    with pytest.raises(ConfigError, match="did not run"):
        quality_line(report)


def test_build_forwards_the_publish_out_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("LAKEHOUSE_HOME", str(tmp_path))
    captured: dict[str, object] = {}
    patch_container(monkeypatch, FakeContainer(FakePipeline()), "build", captured)
    out = tmp_path / "artifact-out"  # type: ignore[operator]

    result = runner.invoke(app, ["build", "--publish", "--out", str(out)])

    assert result.exit_code == 0
    assert captured == {"publish_out": out}
