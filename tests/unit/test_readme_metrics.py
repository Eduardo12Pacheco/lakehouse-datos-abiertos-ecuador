"""The README metrics table is generated data, not hand-written prose (S23, T16).

``scripts/gen_metrics.py`` builds the bundled sample, reads the dbt manifest and
the published artifact, and writes ``docs/METRICS.json``. These tests pin the
contract between that generated snapshot and both README files: the table is
present, every value matches the snapshot, the mirrors agree and both READMEs
(Spanish ``README.md`` and English ``README.en.md``) respect the 150-line budget.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from tests.unit.project_info import project_version

ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT / "docs" / "METRICS.json"
SCRIPT = ROOT / "scripts" / "gen_metrics.py"
READMES = (ROOT / "README.md", ROOT / "README.en.md")
METRICS_START = "<!-- metrics:start -->"
METRICS_END = "<!-- metrics:end -->"
README_MAX_LINES = 150
MIRROR_TOLERANCE = 0.10

# Metric label used in both README tables -> key in docs/METRICS.json.
LABELS: Mapping[str, str] = {
    "dbt models": "models",
    "dbt data tests": "data_tests",
    "dbt unit tests": "unit_tests",
    "pytest tests (default suite)": "pytest_tests",
    "browser e2e tests": "e2e_tests",
    "bundled sample payload files": "sample_payload_files",
    "bundled sample size (bytes)": "sample_size_bytes",
    "rows in raw": "raw_rows",
    "rows in staging models": "staging_rows",
    "rows in intermediate models": "intermediate_rows",
    "rows in marts": "mart_rows",
    "tables in the published artifact": "artifact_tables",
}

REQUIRED_KEYS = {
    "schema_version",
    "package_version",
    "artifact_version",
    "models",
    "data_tests",
    "unit_tests",
    "pytest_tests",
    "e2e_tests",
    "sample_payload_files",
    "sample_size_bytes",
    "raw_rows",
    "staging_rows",
    "intermediate_rows",
    "mart_rows",
    "artifact_tables",
}


def _load_metrics() -> dict[str, object]:
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def _table_rows(text: str, *, path: Path) -> dict[str, str]:
    assert text.count(METRICS_START) == 1, f"{path.name} needs exactly one metrics marker pair"
    assert text.count(METRICS_END) == 1, f"{path.name} needs exactly one metrics marker pair"
    block = text.split(METRICS_START, 1)[1].split(METRICS_END, 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 2 or cells[0].lower() in {"metric", "métrica"}:
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows[cells[0].strip("`")] = cells[1]
    return rows


def _number(value: str) -> int:
    match = re.fullmatch(r"\s*([\d,]+)(?:\s+bytes)?\s*", value)
    assert match is not None, f"metric value {value!r} is not an integer"
    return int(match.group(1).replace(",", ""))


def test_metrics_snapshot_has_every_required_key() -> None:
    metrics = _load_metrics()
    assert set(metrics) >= REQUIRED_KEYS, f"missing metrics: {sorted(REQUIRED_KEYS - set(metrics))}"
    assert metrics["schema_version"] == 1
    assert metrics["package_version"] == project_version()
    for key in REQUIRED_KEYS - {"schema_version", "package_version", "artifact_version"}:
        assert isinstance(metrics[key], int), f"{key} must be an integer"
        assert metrics[key] > 0, f"{key} must be positive"


def test_readmes_embed_the_generated_metrics_table() -> None:
    metrics = _load_metrics()
    for path in READMES:
        assert path.is_file(), f"missing {path.name}"
        rows = _table_rows(path.read_text(encoding="utf-8"), path=path)
        assert set(rows) == set(LABELS), f"{path.name} metric labels drifted from the generator"
        for label, key in LABELS.items():
            assert _number(rows[label]) == metrics[key], (
                f"{path.name} {label!r} is {rows[label]!r}, expected {metrics[key]}"
            )


def test_generator_check_mode_accepts_the_committed_readmes() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "metrics: OK" in completed.stdout


def test_readmes_share_one_table_and_respect_the_line_budget() -> None:
    spanish, english = (path.read_text(encoding="utf-8") for path in READMES)
    spanish_lines = len(spanish.splitlines())
    english_lines = len(english.splitlines())
    assert spanish_lines <= README_MAX_LINES, f"README.md has {spanish_lines} lines"
    assert english_lines <= README_MAX_LINES, f"README.en.md has {english_lines} lines"
    assert abs(spanish_lines - english_lines) <= MIRROR_TOLERANCE * english_lines, (
        f"README.md has {spanish_lines} lines, README.en.md has {english_lines}"
    )
    assert _table_rows(spanish, path=READMES[0]) == _table_rows(english, path=READMES[1])
