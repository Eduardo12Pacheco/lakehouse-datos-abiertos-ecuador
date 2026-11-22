"""Tests for the ``lakehouse fetch`` command wiring (S1, S4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.unit.cli_support import plain
from typer.testing import CliRunner

from ecuador_lakehouse.application.ports import FetchResult
from ecuador_lakehouse.cli.app import app
from ecuador_lakehouse.config import Settings
from ecuador_lakehouse.domain.errors import SourceUnavailableError
from ecuador_lakehouse.domain.sources import SourceFile, SourceId

runner = CliRunner()
SHA = "b" * 64


def make_source_file(partition: str = "2025") -> SourceFile:
    return SourceFile(
        source_id=SourceId.SRI_TAX,
        partition=partition,
        url=f"https://descargas.sri.gob.ec/download/datosAbiertos/sri_{partition}.csv",
        filename=f"sri_{partition}.csv",
        size_bytes=10,
        sha256=SHA,
    )


@dataclass
class RecordingAcquire:
    calls: list[tuple[SourceId, tuple[str, ...], bool]]
    results: list[FetchResult]

    def execute(
        self,
        source_id: SourceId,
        partitions: tuple[str, ...] | None = None,
        *,
        accept_new_vintage: bool = False,
    ) -> list[FetchResult]:
        self.calls.append((source_id, partitions or (), accept_new_vintage))
        return self.results


@dataclass
class FakeContainer:
    settings: Settings
    acquire_sources: RecordingAcquire

    def close(self) -> None:
        pass


def patch_container(monkeypatch: pytest.MonkeyPatch, container: FakeContainer) -> None:
    monkeypatch.setattr(
        "ecuador_lakehouse.cli.commands.fetch.build_container",
        lambda settings=None: container,
    )


def test_fetch_help_lists_the_documented_options() -> None:
    result = runner.invoke(app, ["fetch", "--help"])

    output = plain(result.stdout)
    assert result.exit_code == 0
    assert "--source" in output
    assert "--years" in output
    assert "--accept-new-vintage" in output


def test_fetch_invokes_the_acquire_use_case_and_prints_sha256(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_file = make_source_file()
    acquire = RecordingAcquire(
        calls=[],
        results=[
            FetchResult(
                source_file=source_file,
                path=tmp_path / "sri_2025.csv",
                sha256=SHA,
                size_bytes=10,
                from_cache=False,
                checksum_verified=True,
            )
        ],
    )
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(app, ["fetch", "--source", "sri", "--years", "2025"])

    assert result.exit_code == 0
    assert "sha256 OK" in result.stdout
    assert SHA[:8] in result.stdout
    assert acquire.calls == [(SourceId.SRI_TAX, ("2025",), False)]


def test_fetch_accepts_a_year_range(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    acquire = RecordingAcquire(calls=[], results=[])
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(app, ["fetch", "--source", "sri", "--years", "2024-2025"])

    assert result.exit_code == 0
    assert acquire.calls[0][1] == ("2024", "2025")


def test_fetch_forwards_accept_new_vintage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    acquire = RecordingAcquire(calls=[], results=[])
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(
        app, ["fetch", "--source", "sri", "--years", "2026", "--accept-new-vintage"]
    )

    assert result.exit_code == 0
    assert acquire.calls[0][2] is True


def test_fetch_uses_all_pinned_partitions_for_non_sri_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    acquire = RecordingAcquire(calls=[], results=[])
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(app, ["fetch", "--source", "bce"])

    assert result.exit_code == 0
    assert acquire.calls == [(SourceId.BCE_CNT, (), False)]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--source", "bogus"], "source"),
        (["--source", "sri", "--years", "2017,bogus"], "years"),
        (["--source", "bce", "--years", "2024"], "years"),
    ],
)
def test_invalid_fetch_arguments_exit_two(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arguments: list[str],
    message: str,
) -> None:
    acquire = RecordingAcquire(calls=[], results=[])
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(app, ["fetch", *arguments])

    assert result.exit_code == 2
    assert message in result.output
    assert "Traceback" not in result.output


def test_a_source_unavailable_error_exits_five_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingAcquire(RecordingAcquire):
        def execute(
            self,
            source_id: SourceId,
            partitions: tuple[str, ...] | None = None,
            *,
            accept_new_vintage: bool = False,
        ) -> list[FetchResult]:
            raise SourceUnavailableError("no route to host")

    container = FakeContainer(
        settings=Settings(home=tmp_path),
        acquire_sources=FailingAcquire(calls=[], results=[]),
    )
    patch_container(monkeypatch, container)

    result = runner.invoke(app, ["fetch", "--source", "sri", "--years", "2025"])

    assert result.exit_code == 5
    assert "no route to host" in result.output
    assert "Traceback" not in result.output


def test_fetch_reports_cached_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source_file = make_source_file("2025")
    acquire = RecordingAcquire(
        calls=[],
        results=[
            FetchResult(
                source_file=source_file,
                path=tmp_path / "sri_2025.csv",
                sha256=SHA,
                size_bytes=10,
                from_cache=True,
                checksum_verified=True,
            )
        ],
    )
    patch_container(
        monkeypatch, FakeContainer(settings=Settings(home=tmp_path), acquire_sources=acquire)
    )

    result = runner.invoke(app, ["fetch", "--source", "sri", "--years", "2025"])

    assert result.exit_code == 0
    assert "cached" in result.stdout


def test_fetch_cli_is_registered_once() -> None:
    names = [command.name for command in app.registered_commands]

    assert names.count("fetch") == 1
