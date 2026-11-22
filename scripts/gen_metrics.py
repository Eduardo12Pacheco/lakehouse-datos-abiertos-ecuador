"""Generate the honest README metrics (S23, T16).

The metrics table in ``README.md`` (Spanish) and ``README.en.md`` is produced from a real
sample build, never typed by hand. This script:

1. builds a disposable sample lakehouse with the bundled data (or reuses
   ``--home``), publishing the artifact so its table count is measured too;
2. reads the dbt manifest and the quality-gate results for model and test
   counts;
3. counts the bundled sample payload and the rows in every layer;
4. writes ``docs/METRICS.json`` and prints the Markdown table for the READMEs.

Usage::

    uv run python scripts/gen_metrics.py
    uv run python scripts/gen_metrics.py --home /path/to/lakehouse/home
    uv run python scripts/gen_metrics.py --check

``--check`` is the fast mode used by tests and CI: it verifies that both
committed README tables match the committed metric snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb

from ecuador_lakehouse import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS = REPO_ROOT / "docs" / "METRICS.json"
SAMPLE_DIR = REPO_ROOT / "src" / "ecuador_lakehouse" / "sample_data"
READMES = (REPO_ROOT / "README.md", REPO_ROOT / "README.en.md")
METRICS_START = "<!-- metrics:start -->"
METRICS_END = "<!-- metrics:end -->"

# Display label -> (snapshot key, value suffix). Order defines the table order.
TABLE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("dbt models", "models", ""),
    ("dbt data tests", "data_tests", ""),
    ("dbt unit tests", "unit_tests", ""),
    ("pytest tests (default suite)", "pytest_tests", ""),
    ("browser e2e tests", "e2e_tests", ""),
    ("bundled sample payload files", "sample_payload_files", ""),
    ("bundled sample size (bytes)", "sample_size_bytes", ""),
    ("rows in raw", "raw_rows", ""),
    ("rows in staging models", "staging_rows", ""),
    ("rows in intermediate models", "intermediate_rows", ""),
    ("rows in marts", "mart_rows", ""),
    ("tables in the published artifact", "artifact_tables", ""),
)

_COLLECTED = re.compile(r"(\d+)/(\d+) tests collected \((\d+) deselected\)")
_LAYER_SCHEMAS = ("staging", "intermediate", "marts")
_TABLE_CELLS = 2


class MetricsError(RuntimeError):
    """Raised when the metric generation or verification cannot proceed."""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or verify the README metrics.")
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="reuse this LAKEHOUSE_HOME instead of building a disposable one",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify both README tables against docs/METRICS.json without building",
    )
    return parser.parse_args(argv)


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetricsError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetricsError(f"{path} does not contain a JSON object")
    return payload


def _run_build(home: Path, artifact_dir: Path) -> None:
    env = {**os.environ, "LAKEHOUSE_HOME": str(home), "LAKEHOUSE_MODE": "sample"}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ecuador_lakehouse",
            "build",
            "--publish",
            "--out",
            str(artifact_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise MetricsError(f"sample build failed with exit code {completed.returncode}")


def _collect_pytest_counts() -> tuple[int, int]:
    """Return ``(default_suite, browser_e2e)`` test counts without running them."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MetricsError(f"pytest collection failed:\n{completed.stdout}{completed.stderr}")
    match = _COLLECTED.search(completed.stdout)
    if match is None:
        raise MetricsError("pytest did not report a collection summary")
    selected, total, deselected = (int(group) for group in match.groups())
    if total - selected != deselected:
        raise MetricsError("pytest collection summary is inconsistent")
    return selected, total - selected


def _model_counts(manifest: Mapping[str, Any], warehouse: Path) -> tuple[int, dict[str, int]]:
    nodes = manifest.get("nodes")
    if not isinstance(nodes, dict):
        raise MetricsError("dbt manifest has no nodes")
    models = [
        node
        for node in nodes.values()
        if isinstance(node, dict) and node.get("resource_type") == "model"
    ]
    if not models:
        raise MetricsError("dbt manifest has no models")
    counts = dict.fromkeys(_LAYER_SCHEMAS, 0)
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        raw_tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'raw' AND table_type = 'BASE TABLE'"
            ).fetchall()
        ]
        counts["raw"] = sum(
            int(
                connection.execute(
                    f'SELECT count(*) FROM "raw"."{name}"'  # noqa: S608 - names from catalog
                ).fetchone()[0]
            )
            for name in raw_tables
        )
        for node in models:
            schema = str(node.get("schema", ""))
            name = str(node.get("name", ""))
            if schema not in counts or not name:
                raise MetricsError(f"unexpected model relation {schema}.{name}")
            counts[schema] += int(
                connection.execute(
                    f'SELECT count(*) FROM "{schema}"."{name}"'  # noqa: S608 - names from dbt
                ).fetchone()[0]
            )
    finally:
        connection.close()
    return len(models), counts


def _quality_counts(manifest: Mapping[str, Any], target_dir: Path) -> tuple[int, int]:
    unit_tests = manifest.get("unit_tests")
    unit_count = len(unit_tests) if isinstance(unit_tests, dict) else 0
    nodes = manifest.get("nodes")
    data_count = (
        sum(
            1
            for node in nodes.values()
            if isinstance(node, dict) and node.get("resource_type") == "test"
        )
        if isinstance(nodes, dict)
        else 0
    )
    results = _read_json(target_dir / "quality_results.json").get("results")
    if not isinstance(results, list) or len(results) != data_count + unit_count:
        raise MetricsError("quality results do not match the manifest test counts")
    for result in results:
        if not isinstance(result, dict) or str(result.get("status", "")).lower() not in {
            "pass",
            "success",
            "warn",
        }:
            raise MetricsError("the quality gate is not green; refusing to publish metrics")
    return data_count, unit_count


def _sample_counts() -> tuple[int, int]:
    bundle = _read_json(SAMPLE_DIR / "SAMPLE_MANIFEST.json").get("files")
    payload_files = len(bundle) if isinstance(bundle, list) else 0
    total = sum(path.stat().st_size for path in SAMPLE_DIR.iterdir() if path.is_file())
    if payload_files == 0 or total == 0:
        raise MetricsError("the bundled sample is missing")
    return payload_files, total


def _artifact_counts(artifact_dir: Path) -> tuple[str, int]:
    manifests = sorted(artifact_dir.glob("ecuador-lakehouse-*/manifest.json"))
    if len(manifests) != 1:
        raise MetricsError(f"expected one published artifact under {artifact_dir}")
    manifest = _read_json(manifests[0])
    tables = manifest.get("tables")
    version = manifest.get("artifact_version")
    if not isinstance(tables, list) or not isinstance(version, str):
        raise MetricsError("the artifact manifest is incomplete")
    return version, len(tables)


def collect_metrics(home: Path, artifact_dir: Path) -> dict[str, Any]:
    """Build and measure one sample run, returning the snapshot mapping."""
    _run_build(home, artifact_dir)
    target_dir = home / "dbt" / "target"
    manifest = _read_json(target_dir / "manifest.json")
    models, row_counts = _model_counts(manifest, home / "warehouse.duckdb")
    data_tests, unit_tests = _quality_counts(manifest, target_dir)
    sample_files, sample_bytes = _sample_counts()
    pytest_tests, e2e_tests = _collect_pytest_counts()
    artifact_version, artifact_tables = _artifact_counts(artifact_dir)
    return {
        "schema_version": 1,
        "package_version": __version__,
        "artifact_version": artifact_version,
        "models": models,
        "data_tests": data_tests,
        "unit_tests": unit_tests,
        "pytest_tests": pytest_tests,
        "e2e_tests": e2e_tests,
        "sample_payload_files": sample_files,
        "sample_size_bytes": sample_bytes,
        "raw_rows": row_counts["raw"],
        "staging_rows": row_counts["staging"],
        "intermediate_rows": row_counts["intermediate"],
        "mart_rows": row_counts["marts"],
        "artifact_tables": artifact_tables,
    }


def write_metrics(path: Path, metrics: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(metrics), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_table(metrics: Mapping[str, Any]) -> str:
    lines = ["| Metric | Value |", "| --- | ---: |"]
    for label, key, suffix in TABLE_ROWS:
        value = int(metrics[key])
        rendered = f"{value:,}{suffix}"
        lines.append(f"| {label} | {rendered} |")
    return "\n".join(lines)


def _readme_rows(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if text.count(METRICS_START) != 1 or text.count(METRICS_END) != 1:
        raise MetricsError(f"{path.name} needs exactly one metrics marker pair")
    block = text.split(METRICS_START, 1)[1].split(METRICS_END, 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != _TABLE_CELLS or cells[0].lower() in {"metric", "métrica"}:
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows[cells[0].strip("`")] = cells[1]
    return rows


def check_readmes(metrics_path: Path = DEFAULT_METRICS) -> int:
    """Verify both README tables equal the committed snapshot."""
    metrics = _read_json(metrics_path)
    expected = {label: f"{int(metrics[key]):,}" for label, key, _ in TABLE_ROWS}
    checked = 0
    for path in READMES:
        if not path.is_file():
            raise MetricsError(f"missing {path.name}")
        rows = _readme_rows(path)
        if rows != expected:
            raise MetricsError(
                f"{path.name} metrics differ from {metrics_path.name}; "
                "run uv run python scripts/gen_metrics.py"
            )
        checked += len(rows)
    sys.stdout.write(f"metrics: OK ({checked} values across {len(READMES)} README files)\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.check:
        return check_readmes()

    with tempfile.TemporaryDirectory(prefix="lakehouse-metrics-") as scratch:
        root = Path(scratch)
        home: Path = args.home if args.home is not None else root / "home"
        artifact_dir = root / "artifact"
        metrics = collect_metrics(home, artifact_dir)

    write_metrics(DEFAULT_METRICS, metrics)
    sys.stdout.write(render_table(metrics) + "\n")
    sys.stdout.write(f"wrote {DEFAULT_METRICS.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
