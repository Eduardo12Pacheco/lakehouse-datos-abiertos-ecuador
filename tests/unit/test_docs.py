"""Documentation contracts for the S22 documentation set (task T15).

These tests keep the docs honest: links must resolve, every setting and CLI
command must be documented, ADRs must follow the shared template and the
Mermaid fences must be balanced. They are deliberately structural: they do not
try to grade prose, only the guarantees a reader relies on.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from ecuador_lakehouse.cli.app import app
from ecuador_lakehouse.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

REQUIRED_DOCS = (
    "ARCHITECTURE.md",
    "DATA.md",
    "ARTIFACT.md",
    "CONTRACT.md",
    "CONFIGURATION.md",
)

REQUIRED_ADR_HEADINGS = ("Estado", "Contexto", "Decisión", "Consecuencias")

# Links whose target starts with one of these schemes are not local files.
_EXTERNAL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _markdown_files() -> list[Path]:
    files = sorted(DOCS.rglob("*.md"))
    for name in ("README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md"):
        path = ROOT / name
        if path.is_file():
            files.insert(0, path)
    return files


def _iter_links(text: str) -> Iterator[str]:
    """Yield the raw targets of inline Markdown links and images."""
    pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for match in pattern.finditer(text):
        yield match.group(1)


def _local_target(raw: str) -> str | None:
    target = raw.strip()
    if not target:
        return None
    target = target[1:-1] if target.startswith("<") and target.endswith(">") else target.split()[0]
    if not target or target.startswith("#") or _EXTERNAL_SCHEME.match(target):
        return None
    return target.split("#", 1)[0]


@pytest.mark.parametrize("name", REQUIRED_DOCS)
def test_required_document_exists_and_is_substantial(name: str) -> None:
    path = DOCS / name
    assert path.is_file(), f"docs/{name} is missing"
    assert len(path.read_text(encoding="utf-8").strip()) > 500


def test_adr_set_has_at_least_eight_consistent_records() -> None:
    adrs = sorted((DOCS / "adr").glob("*.md"))
    assert len(adrs) >= 8
    for path in adrs:
        text = path.read_text(encoding="utf-8")
        for heading in REQUIRED_ADR_HEADINGS:
            assert re.search(rf"^## {heading}\s*$", text, re.MULTILINE), (
                f"{path.name} is missing the '## {heading}' section"
            )
        assert "ADR" in text.splitlines()[0], f"{path.name} has no ADR title"


def test_every_relative_link_resolves() -> None:
    broken: list[str] = []
    files = _markdown_files()
    assert files, "no Markdown files found"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for raw in _iter_links(text):
            target = _local_target(raw)
            if target is None:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)


def test_every_settings_environment_variable_is_documented() -> None:
    text = (DOCS / "CONFIGURATION.md").read_text(encoding="utf-8")
    missing = [
        f"LAKEHOUSE_{name.upper()}"
        for name in Settings.model_fields
        if f"LAKEHOUSE_{name.upper()}" not in text
    ]
    assert not missing, f"settings missing from docs/CONFIGURATION.md: {missing}"


def _typer_command_names() -> set[str]:
    names: set[str] = set()
    for command in app.registered_commands:
        if command.name:
            names.add(command.name)
    for group in app.registered_groups:
        if group.name:
            names.add(group.name)
        child = group.typer_instance
        if child is not None:
            for command in child.registered_commands:
                if command.name:
                    names.add(command.name)
    return names


def test_every_cli_command_is_documented() -> None:
    text = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    readme = ROOT / "README.md"
    if readme.is_file():
        text += "\n" + readme.read_text(encoding="utf-8")
    names = _typer_command_names()
    assert {"build", "test", "serve", "fetch", "publish", "verify"} <= names
    missing = sorted(name for name in names if name not in text)
    assert not missing, f"CLI commands missing from docs: {missing}"


def test_mermaid_fences_are_balanced() -> None:
    for path in _markdown_files():
        in_fence: str | None = None
        mermaid_blocks = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("```"):
                continue
            if in_fence is None:
                in_fence = stripped[3:].strip() or "text"
                if in_fence == "mermaid":
                    mermaid_blocks += 1
            else:
                in_fence = None
        assert in_fence is None, f"{path.relative_to(ROOT)} has an unclosed code fence"
        if path.name in {"ARCHITECTURE.md", "LINEAGE.md"}:
            assert mermaid_blocks >= 1, f"{path.relative_to(ROOT)} has no Mermaid diagram"


def test_architecture_names_the_patterns_and_data_model() -> None:
    text = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for pattern in (
        "Ports & Adapters",
        "Strategy",
        "Factory",
        "Repository",
        "Unit of Work",
        "Pipeline",
        "Value Objects",
        "Specification",
    ):
        assert pattern in text, f"pattern not named in ARCHITECTURE.md: {pattern}"
    assert text.count("```mermaid") >= 3
    for entity in (
        "dim_date",
        "dim_quarter",
        "dim_geography",
        "dim_tax_item",
        "dim_price_area",
        "dim_cpi_item",
        "dim_national_account_item",
        "fct_tax_collection",
        "fct_cpi_index",
        "fct_national_accounts",
        "mart_tax_collection_monthly",
        "mart_inflation_monthly",
        "mart_tax_to_gdp_annual",
        "mart_tax_lifecycle",
    ):
        assert entity in text, f"data model entity missing from ARCHITECTURE.md: {entity}"


def test_data_document_states_the_limitations() -> None:
    text = (DOCS / "DATA.md").read_text(encoding="utf-8").lower()
    for phrase in (
        "presión fiscal",
        "2024",
        "2021q1",
        "scd2",
        "provincial",
        "limitaciones",
    ):
        assert phrase in text, f"limitation missing from DATA.md: {phrase}"


def test_artifact_and_contract_documents_cover_consumption() -> None:
    artifact = (DOCS / "ARTIFACT.md").read_text(encoding="utf-8")
    contract = (DOCS / "CONTRACT.md").read_text(encoding="utf-8")
    for phrase in ("ATTACH", "manifest.json", "SHA256SUMS", "READ_ONLY", "content_sha256"):
        assert phrase in artifact, f"ARTIFACT.md does not document {phrase}"
    for phrase in ("MAJOR", "MINOR", "PATCH", "artifact_contract.json"):
        assert phrase in contract, f"CONTRACT.md does not document {phrase}"


def test_adrs_evaluate_the_rejected_alternatives() -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((DOCS / "adr").glob("*.md"))
    ).lower()
    for term in ("dagster", "evidence.dev", "streamlit", "postgres", "polars", "snapshot"):
        assert term in corpus, f"alternatives analysis missing: {term}"


def test_docs_have_no_placeholder_markers() -> None:
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        # Markers are uppercase: "todo" is an ordinary Spanish word.
        assert not re.search(r"\b(?:TODO|FIXME)\b", text), (
            f"placeholder marker found in {path.relative_to(ROOT)}"
        )
        assert not re.search(r"lorem", text, re.IGNORECASE), (
            f"placeholder text found in {path.relative_to(ROOT)}"
        )
