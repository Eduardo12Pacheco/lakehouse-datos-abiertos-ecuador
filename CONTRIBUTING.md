# Contributing

Thanks for your interest in improving the Ecuador open-data lakehouse.

## Development setup

Prerequisites: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run lakehouse --version
uv run python scripts/dev.py check
```

`scripts/dev.py` is the cross-platform entry point for the quality gates:

| Task | What it runs |
| --- | --- |
| `check` | `lint`, `format`, `arch`, `types`, `test` |
| `lint` | `ruff check .` |
| `format` | `ruff format --check .` |
| `arch` | `import-linter` (hexagonal layer contracts) |
| `types` | `mypy` (strict, `src/` only) |
| `test` | `pytest` (browser tests are excluded unless marked `e2e`) |
| `fix` | `ruff check --fix .` then `ruff format .` |

The first command to run after a change is the focused pytest file; the last is
`uv run python scripts/dev.py check`. CI additionally runs `uv lock --check`,
the test suite on Linux, Windows and macOS, the browser suite, an installer
smoke test and the security jobs. Run locally before opening a pull request:

```bash
uv lock --check
uv run python scripts/dev.py check
uv run pytest -m e2e
uv build && uv run python scripts/smoke.py dist/*.whl
```

## Tests

- Write the failing test first, then the implementation. Observe RED before
  GREEN.
- Tests must be deterministic and offline; an autouse fixture blocks every
  non-loopback socket connection. Use `tmp_path` for scratch state and never
  write into the repository.
- Use Hypothesis for data invariants (DAG ordering, text normalization,
  parser encoding parity, partition load order, SCD2 integrity) and keep
  `deadline=None` for dbt-backed properties.
- Integration tests use real DuckDB and real dbt; do not mock the warehouse.
- Browser tests live under `tests/e2e` behind the `e2e` marker. Install
  Chromium once with `uv run playwright install chromium`.
- Never weaken, skip or delete a test to make the suite green.

## Architecture and documentation

The dependency rule is `cli -> container -> adapters -> application -> domain`.
`domain/` imports only the standard library and itself; `application/` talks to
adapters only through the protocols in `application/ports.py`. If you add a
package, update the import-linter contracts in `pyproject.toml` and the
architecture test in the same change.

When you change behaviour, update the reader-facing docs in the same commit:

| Change | Document |
| --- | --- |
| Layer, port, pattern, pipeline or exit code | `docs/ARCHITECTURE.md` |
| Source, format quirk, sample, measured fact or limitation | `docs/DATA.md` |
| Artifact layout, manifest, verification or consumption | `docs/ARTIFACT.md` |
| Published table, column, type or version rule | `docs/CONTRACT.md` and `artifact_contract.json` |
| Environment variable, default or CLI override | `docs/CONFIGURATION.md` |
| Significant decision with alternatives | New ADR in `docs/adr/` |

ADRs use the template: `Status`, `Context`, `Decision`, `Consequences` and
`Alternatives considered`. Number them sequentially and keep the rejected
options concrete (cost, dependency, operational reason). `uv run pytest
tests/unit/test_docs.py` checks links, settings coverage, CLI coverage, ADR
headings and Mermaid fences.

## Regenerating generated files

All generated files are committed, and every one has a reproducible command.

**Lineage** (requires a built warehouse):

```bash
uv run lakehouse docs --mermaid docs/LINEAGE.md
git diff --exit-code docs/LINEAGE.md   # must be clean after regeneration
```

**Bundled sample** (maintainer only; downloads about 960 MB once):

```bash
uv run lakehouse sample build --cache-dir "$LAKEHOUSE_HOME/cache"
```

The command verifies every pinned SHA-256, writes
`src/ecuador_lakehouse/sample_data/`, regenerates `SAMPLE_MANIFEST.json` and
updates `dbt_project/seeds/control_totals.csv`. Commit the result as a separate
`chore(data): ...` commit and include the observed row counts in the log.
Never commit an upstream file or a cache directory.

**Media** (requires Chromium):

```bash
uv run python scripts/capture_media.py
```

The script builds a disposable sample lakehouse, captures eight 1440x900 PNGs
in `docs/media/` and assembles `demo.gif` from the pages, asserting each frame
is non-blank and the GIF stays within the size budget.

**README metrics** (requires a sample build; no network):

```bash
uv run python scripts/gen_metrics.py
```

The script builds and publishes a disposable sample lakehouse, reads the dbt
manifest, the quality results and the artifact, then rewrites
`docs/METRICS.json`. Paste the printed table into both `README.md` and
`README.en.md` between the `metrics:start`/`metrics:end` markers. Verify with
`uv run python scripts/gen_metrics.py --check`; never edit a metric by hand.

**Vendored ECharts**:

```bash
uv run python scripts/vendor_echarts.py
```

The script downloads the pinned ECharts 6.1.0 bundle, verifies its size and
SHA-256 and writes the license and notice files. Do not vendor another version
without updating the pinned checksum and the ADR.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) in English:
  `feat(cli): add serve command`, `fix(parsers): handle cp1252 SRI files`,
  `docs(architecture): document the artifact contract`.
- Keep commits focused and reviewable (roughly 400 changed lines or fewer,
  generated data excluded). Put generated sample bytes in their own commit.
- Do not add AI attribution or `Co-Authored-By` trailers.
- Every pull request must pass lint, type checks and the test matrix on Linux,
  Windows and macOS before merging.
- Update `CHANGELOG.md` under `Unreleased` for user-visible changes.

## Releasing

1. Bump `version` in `pyproject.toml` and the fallback in
   `src/ecuador_lakehouse/__init__.py`, then run `uv lock`. Re-run
   `uv run lakehouse sample build` (with `--cache-dir` pointing at the verified
   upstream cache to stay offline): `SAMPLE_MANIFEST.json` records the builder
   version and a test pins it to the package version.
2. Move the `Unreleased` entries of `CHANGELOG.md` under the new version and
   update the release-wheel URL in both READMEs.
3. Refresh the metrics snapshot (`uv run python scripts/gen_metrics.py`) and
   commit.
4. Push a `vX.Y.Z` tag. `release.yml` fails fast when the tag and the package
   version differ, re-runs CI, builds the wheel, sdist and sample artifact zip,
   writes `SHA256SUMS` and creates the GitHub release.

## Reporting security issues

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).
