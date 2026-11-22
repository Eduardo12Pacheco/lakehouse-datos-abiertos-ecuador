"""Integration tests for the generated static report site (S16)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from ecuador_lakehouse.adapters.report.reader import DuckDbReportReader
from ecuador_lakehouse.adapters.report.renderer import JinjaReportRenderer
from ecuador_lakehouse.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from ecuador_lakehouse.application.use_cases.build_report import BuildReport
from ecuador_lakehouse.container import load_lockfile
from tests.integration.conftest import StagingBuild

PAGES = {
    "index": "index",
    "tax": "tax",
    "prices": "prices",
    "macro": "macro",
    "quality": "quality",
    "sources": "sources",
    "empty": "empty",
}
ECHARTS_SHA256 = "b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0"
ECHARTS_BYTES = 1_121_883
_DATA_BLOCK = re.compile(
    r'<script type="application/json" id="data-(?P<page>[a-z]+)">(?P<payload>.*?)</script>',
    re.DOTALL,
)
_REMOTE_ASSET = re.compile(r'<(?:script|link)[^>]+(?:src|href)="https?://', re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReportSite:
    """A generated report site plus the data snapshot that produced it."""

    site: Path
    files: dict[str, str]


@pytest.fixture(scope="module")
def report_site(marts_build: StagingBuild, tmp_path_factory: pytest.TempPathFactory) -> ReportSite:
    """Render the full site from the session sample warehouse, with real run results."""
    marts_build.transformer.test()
    # Mirror the real pipeline order: docs generate rewrites run_results.json.
    marts_build.transformer.docs()
    site = tmp_path_factory.mktemp("report-site")
    warehouse = DuckDbWarehouse(marts_build.warehouse_path)
    use_case = BuildReport(
        warehouse=warehouse,
        reader=DuckDbReportReader(
            warehouse_path=marts_build.warehouse_path,
            dbt_target_dir=marts_build.transformer.target_dir,
        ),
        renderer=JinjaReportRenderer(),
        lockfile=load_lockfile(),
        site_dir=site,
        mode="sample",
    )
    try:
        use_case.execute()
    finally:
        warehouse.close()
    files = {path.name: path.read_text(encoding="utf-8") for path in site.glob("*.html")}
    return ReportSite(site=site, files=files)


def test_every_page_is_generated(report_site: ReportSite) -> None:
    assert set(report_site.files) == {f"{name}.html" for name in PAGES}
    assert (report_site.site / "assets" / "app.css").is_file()
    assert (report_site.site / "assets" / "tokens.css").is_file()
    assert (report_site.site / "assets" / "app.js").is_file()
    assert (report_site.site / "assets" / "echarts.min.js").is_file()
    assert (report_site.site / "assets" / "ECHARTS_LICENSE").is_file()
    assert (report_site.site / "report.json").is_file()


def test_vendored_echarts_matches_the_pinned_release() -> None:
    asset = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ecuador_lakehouse"
        / "adapters"
        / "report"
        / "assets"
        / "echarts.min.js"
    )
    payload = asset.read_bytes()
    assert len(payload) == ECHARTS_BYTES
    assert hashlib.sha256(payload).hexdigest() == ECHARTS_SHA256


@pytest.mark.parametrize(("name", "page"), list(PAGES.items()))
def test_page_embeds_one_parseable_data_block(
    report_site: ReportSite, name: str, page: str
) -> None:
    html = report_site.files[f"{name}.html"]
    blocks = [match for match in _DATA_BLOCK.finditer(html) if match.group("page") == page]
    assert len(blocks) == 1, f"{name}.html must embed exactly one data-{page} block"
    payload = json.loads(blocks[0].group("payload"))
    assert isinstance(payload, dict)
    assert payload
    assert "</script>" not in blocks[0].group("payload")


def test_pages_never_load_remote_assets(report_site: ReportSite) -> None:
    for name, html in report_site.files.items():
        assert not _REMOTE_ASSET.search(html), f"{name}.html loads a remote script or stylesheet"
        local_assets = (
            "assets/tokens.css",
            "assets/app.css",
            "assets/echarts.min.js",
            "assets/app.js",
        )
        for asset in local_assets:
            assert asset in html, f"{name}.html does not reference {asset}"
        assert 'href="lineage/index.html"' in html


def test_overview_data_has_kpis_and_monthly_series(report_site: ReportSite) -> None:
    data = _payload(report_site, "index", "index")
    assert data["kpis"]["latest_full_year"] == 2025
    assert data["kpis"]["latest_full_year_total_usd"] > 21_000_000_000
    assert 0.02 < data["kpis"]["latest_full_year_yoy"] < 0.12
    assert data["kpis"]["inflation_dec_2024"] == pytest.approx(0.005281059792338061)
    assert data["kpis"]["ratio_2020"] > 0.05
    assert data["kpis"]["tests_passed"] >= 260
    assert data["monthly"][0]["date"] == "2017-01-01"
    assert len(data["monthly"]) >= 110


def test_tax_data_covers_every_year_and_province(report_site: ReportSite) -> None:
    data = _payload(report_site, "tax", "tax")
    assert data["years"] == list(range(2017, 2027))
    assert len(data["groups"]) >= 3
    assert len(data["top_lines"]) == 10
    assert data["top_lines"][0]["tax_name"] == "IVA MENSUAL"
    assert set(data["provinces"]) == {str(year) for year in range(2017, 2027)}
    assert len(data["provinces"]["2025"]) == 25
    assert sum(row["nominal_usd"] for row in data["monthly"]) > 0


def test_prices_data_includes_areas_and_divisions(report_site: ReportSite) -> None:
    data = _payload(report_site, "prices", "prices")
    assert data["latest_month"] == "2024-12"
    assert len(data["areas"]) == 12
    assert {row["area"] for row in data["series"]} == set(data["areas"])
    assert len([row for row in data["series"] if row["area"] == "Nacional"]) == 120
    assert data["divisions"]
    assert {row["area"] for row in data["divisions"]} == set(data["areas"])


def test_macro_data_has_industries_and_ratio(report_site: ReportSite) -> None:
    data = _payload(report_site, "macro", "macro")
    assert data["years"][0] == 2000
    assert data["years"][-1] == 2021
    assert len({row["name"] for row in data["industries"]}) == 45
    complete = [row for row in data["ratios"] if row["is_complete"]]
    assert [row["year"] for row in complete] == [2017, 2018, 2019, 2020]
    assert all(0.05 < row["ratio"] < 0.25 for row in complete)


def test_quality_data_reflects_real_run_results(report_site: ReportSite) -> None:
    data = _payload(report_site, "quality", "quality")
    assert data["tests"]["total"] == 265
    assert data["tests"]["failed"] == 0
    layers = {row["layer"] for row in data["tests"]["layers"]}
    assert {"staging", "intermediate", "marts", "reconciliation", "unit"}.issubset(layers)
    assert len(data["batches"]) == 12
    assert data["row_counts"]
    assert {row["layer"] for row in data["row_counts"]} >= {
        "raw",
        "staging",
        "intermediate",
        "marts",
    }


def test_sources_data_is_the_pinned_inventory(report_site: ReportSite) -> None:
    data = _payload(report_site, "sources", "sources")
    assert len(data["files"]) == 12
    assert data["checked_at"] == "2026-11-19"
    assert all(len(row["sha256"]) == 64 for row in data["files"])
    assert all(row["license_id"].startswith("cc-by") for row in data["files"])
    assert data["licenses"]["sri_tax"] == "cc-by"


def test_empty_page_documents_the_empty_state(report_site: ReportSite) -> None:
    html = report_site.files["empty.html"]
    assert "No data" in html or "no data" in html
    assert 'id="empty-state"' in report_site.files["index.html"]


def _payload(report_site: ReportSite, name: str, page: str) -> dict[str, object]:
    html = report_site.files[f"{name}.html"]
    match = _DATA_BLOCK.search(html)
    assert match is not None
    assert match.group("page") == page
    payload = json.loads(match.group("payload"))
    assert isinstance(payload, dict)
    return payload
