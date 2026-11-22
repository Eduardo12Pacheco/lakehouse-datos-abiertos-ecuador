"""Unit tests for the report reader error boundaries (S16)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecuador_lakehouse.adapters.report.reader import DuckDbReportReader, _quality_rows
from ecuador_lakehouse.domain.errors import ConfigError


@pytest.mark.parametrize(
    ("original_file_path", "layer"),
    [
        ("models/staging/schema.yml", "staging"),
        ("models\\staging\\schema.yml", "staging"),
        ("models\\marts\\schema.yml", "marts"),
        ("tests\\assert_no_future_periods.sql", "reconciliation"),
    ],
)
def test_quality_rows_classify_dbt_paths_with_either_separator(
    tmp_path: Path, original_file_path: str, layer: str
) -> None:
    """dbt writes OS-native separators, so a Windows path must classify like a POSIX one."""
    test_id = "test.lakehouse.some_check"
    (tmp_path / "run_results.json").write_text(
        json.dumps({"results": [{"unique_id": test_id, "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"nodes": {test_id: {"name": "some_check", "original_file_path": original_file_path}}}
        ),
        encoding="utf-8",
    )

    rows = _quality_rows(tmp_path)

    assert [row["layer"] for row in rows] == [layer]


def test_missing_warehouse_is_a_config_error(tmp_path: Path) -> None:
    reader = DuckDbReportReader(
        warehouse_path=tmp_path / "warehouse.duckdb",
        dbt_target_dir=tmp_path / "dbt" / "target",
    )
    with pytest.raises(ConfigError, match="lakehouse build"):
        reader.read(mode="sample")


def test_warehouse_without_marts_is_a_config_error(tmp_path: Path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    warehouse.write_bytes(b"")
    reader = DuckDbReportReader(
        warehouse_path=warehouse,
        dbt_target_dir=tmp_path / "dbt" / "target",
    )
    with pytest.raises(ConfigError, match="lakehouse build"):
        reader.read(mode="sample")
