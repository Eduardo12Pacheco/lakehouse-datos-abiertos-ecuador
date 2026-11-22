"""Read-only DuckDB adapter that builds the report snapshot (S16).

All SQL and all DuckDB knowledge stay in this adapter. The site only receives
JSON-ready rows: dates become ISO strings, decimals become floats and every
table is aggregated exactly once during the build.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

from ecuador_lakehouse.domain.errors import ConfigError
from ecuador_lakehouse.domain.report import ReportSnapshot

_REQUIRED_MARTS = (
    "mart_tax_collection_monthly",
    "mart_tax_lifecycle",
    "mart_tax_to_gdp_annual",
    "mart_inflation_monthly",
    "fct_tax_collection",
    "dim_geography",
    "fct_national_accounts",
    "dim_national_account_item",
)

_LAYER_BY_PREFIX = (
    ("models/staging/", "staging"),
    ("models/intermediate/", "intermediate"),
    ("models/marts/", "marts"),
    ("tests/", "reconciliation"),
    ("seeds/", "seeds"),
)

_PASSING = frozenset({"success", "pass", "warn"})


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> tuple[dict[str, object], ...]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description or ()]
    return tuple(
        {column: _json_value(value) for column, value in zip(columns, raw, strict=True)}
        for raw in cursor.fetchall()
    )


def _classify(path: str) -> str:
    # dbt writes OS-native separators in ``original_file_path``; normalize them.
    normalized = path.replace("\\", "/")
    for prefix, layer in _LAYER_BY_PREFIX:
        if normalized.startswith(prefix):
            return layer
    return "other"


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _quality_rows(target_dir: Path) -> tuple[dict[str, object], ...]:
    quality_results = target_dir / "quality_results.json"
    source = quality_results if quality_results.is_file() else target_dir / "run_results.json"
    run_results = _read_json(source)
    manifest = _read_json(target_dir / "manifest.json")
    raw_nodes = manifest.get("nodes")
    nodes: Mapping[str, Mapping[str, object]] = (
        {str(key): value for key, value in raw_nodes.items() if isinstance(value, dict)}
        if isinstance(raw_nodes, dict)
        else {}
    )
    raw_results = run_results.get("results")
    if not isinstance(raw_results, list):
        return ()
    rows: list[dict[str, object]] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        unique_id = str(raw.get("unique_id", ""))
        if not unique_id.startswith(("test.", "unit_test.")):
            continue
        node = nodes.get(unique_id, {})
        if unique_id.startswith("unit_test."):
            layer = "unit"
        else:
            layer = _classify(str(node.get("original_file_path", "")))
        status = str(raw.get("status", "error")).lower()
        rows.append(
            {
                "name": str(node.get("name", unique_id.rsplit(".", 1)[-1])),
                "node": unique_id,
                "layer": layer,
                "passed": status in _PASSING,
                "status": "passed" if status in _PASSING else "failed",
            }
        )
    return tuple(rows)


class DuckDbReportReader:
    """``ReportReader`` implementation over a read-only DuckDB connection."""

    def __init__(self, *, warehouse_path: Path, dbt_target_dir: Path) -> None:
        self._warehouse_path = Path(warehouse_path)
        self._target_dir = Path(dbt_target_dir)

    def read(self, *, mode: str) -> ReportSnapshot:
        """Aggregate every marts query needed by the six report pages."""
        if not self._warehouse_path.is_file():
            raise ConfigError("No data yet - run: lakehouse build")
        try:
            connection = duckdb.connect(str(self._warehouse_path), read_only=True)
        except (duckdb.Error, OSError) as exc:
            raise ConfigError("No data yet - run: lakehouse build") from exc
        try:
            self._ensure_marts(connection)
            return ReportSnapshot(
                mode=mode,
                tax_monthly=_rows(
                    connection,
                    """
                    select period_year, period_month, period_date, tax_group_name,
                           nominal_usd, real_usd_2014, yoy_nominal
                    from marts.mart_tax_collection_monthly
                    order by period_date, tax_group_name
                    """,
                ),
                tax_lifecycle=_rows(
                    connection,
                    """
                    select tax_name, tax_group_name, total_collected_usd,
                           first_year, last_year, years_active, versions_count, current_status
                    from marts.mart_tax_lifecycle
                    order by total_collected_usd desc, tax_name
                    limit 10
                    """,
                ),
                tax_provinces=_rows(
                    connection,
                    """
                    select facts.period_year, geography.province_name,
                           sum(facts.collected_usd) as collected_usd
                    from marts.fct_tax_collection as facts
                    inner join marts.dim_geography as geography
                        on geography.geography_key = facts.geography_key
                    group by facts.period_year, geography.province_name
                    order by facts.period_year, collected_usd desc
                    """,
                ),
                inflation=_rows(
                    connection,
                    """
                    select price_area_name, level, ccif_name, period_date, index_value, mom, yoy
                    from marts.mart_inflation_monthly
                    where level in ('general', 'division')
                    order by price_area_name, level, period_date
                    """,
                ),
                gdp_industries=_rows(
                    connection,
                    """
                    select facts.period_year as year, items.item_name as name,
                           sum(facts.value_thousand_usd) * 1000 as value_usd
                    from marts.fct_national_accounts as facts
                    inner join marts.dim_national_account_item as items
                        on items.account_item_key = facts.account_item_key
                    where items.kind = 'industry' and facts.price_basis = 'current'
                    group by facts.period_year, items.item_name
                    order by facts.period_year, value_usd desc
                    """,
                ),
                tax_to_gdp=_rows(
                    connection,
                    """
                    select period_year, sri_collection_usd, gdp_current_usd, ratio,
                           quarters_available, months_available, is_complete
                    from marts.mart_tax_to_gdp_annual
                    order by period_year
                    """,
                ),
                quality_tests=_quality_rows(self._target_dir),
                batches=_rows(
                    connection,
                    """
                    select batch_id, source_id, partition_key, source_sha256, row_count,
                           status, mode, loaded_at
                    from meta.batches
                    where is_current
                    order by source_id, partition_key
                    """,
                ),
                row_counts=self._row_counts(connection),
            )
        finally:
            connection.close()

    def _ensure_marts(self, connection: duckdb.DuckDBPyConnection) -> None:
        placeholders = ", ".join("?" for _ in _REQUIRED_MARTS)
        count = connection.execute(
            "select count(*) from information_schema.tables "  # noqa: S608 - literal catalog query
            f"where table_schema = 'marts' and table_name in ({placeholders})",
            list(_REQUIRED_MARTS),
        ).fetchone()
        if count is None or count[0] != len(_REQUIRED_MARTS):
            raise ConfigError("No data yet - run: lakehouse build")

    def _row_counts(self, connection: duckdb.DuckDBPyConnection) -> tuple[dict[str, object], ...]:
        tables = _rows(
            connection,
            """
            select table_schema as layer, table_name
            from information_schema.tables
            where table_schema in ('raw', 'staging', 'intermediate', 'marts')
            order by case table_schema
                when 'raw' then 1
                when 'staging' then 2
                when 'intermediate' then 3
                else 4
            end, table_name
            """,
        )
        rows: list[dict[str, object]] = []
        for table in tables:
            layer = str(table["layer"])
            name = str(table["table_name"])
            count = connection.execute(
                f'select count(*) from "{layer}"."{name}"'  # noqa: S608 - names come from the catalog
            ).fetchone()
            rows.append(
                {
                    "layer": layer,
                    "table": name,
                    "rows": int(count[0]) if count is not None else 0,
                }
            )
        return tuple(rows)
