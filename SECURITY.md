# Security policy

## Supported versions

The project is pre-1.0. Security fixes are applied to the latest release on
`main`; older snapshots are not maintained. The published data artifact follows
its own contract version (see [docs/CONTRACT.md](docs/CONTRACT.md)); a security
fix to the software may ship without changing the data contract.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use the repository's
**Security** tab to open a private advisory
(<https://github.com/Eduardo12Pacheco/lakehouse-datos-abiertos-ecuador/security/advisories/new>)
and include:

- the affected version and command,
- a minimal reproduction,
- the impact you expect,
- any known mitigation.

You can expect an acknowledgement within a few days. Once a fix is available a
new release is published and the advisory is disclosed with credit, if desired.
Please give the project a reasonable window to release a fix before publishing
details.

## Scope

The tool is local-first and single-user. In scope:

- the Python package, CLI and bundled sample,
- the dbt project and the data-quality gate,
- the static report site and `lakehouse serve`,
- the published artifact format and `lakehouse verify`,
- the CI and release workflows in this repository.

Out of scope: vulnerabilities in DuckDB, dbt, httpx, Jinja2, ECharts or the
host operating system (report them upstream, but tell us if this project's
usage makes them exploitable), and attacks that require an already-compromised
local account or physical access.

## Design guarantees

### No credentials or accounts

The tool runs locally and never requires credentials, API keys, tokens or
accounts. There is no secret environment variable, no login flow and no paid
API. Downloads use public, key-free source hosts only.

### Verified, constrained downloads

- Requests are restricted to an allow-list of public data hosts:
  `descargas.sri.gob.ec`, `www.ecuadorencifras.gob.ec`,
  `www.datosabiertos.gob.ec` and `datosabiertos.gob.ec`.
- Redirects are validated against the same allow-list; a redirect outside it is
  refused.
- Every file is capped at 300 MiB and verified against a pinned SHA-256 from
  `sources.lock.json` before it is used. An immutable mismatch raises
  `ChecksumMismatchError` (exit 3).
- The only mutable file is the current SRI year. A changed checksum emits a
  warning and is recorded as a new vintage only with `--accept-new-vintage`.
- Downloads can resume from a `.part` file, and a partial or mismatched file is
  never loaded into the warehouse.

### Archive handling

The INEC source is a nested ZIP. Before any bytes are written, members are
checked for:

- path traversal (`..`), absolute paths, backslashes and symlinks;
- a per-member uncompressed cap of 300 MiB and a total cap of 600 MiB;
- a decompression ratio above 200x, which is rejected as a bomb.

Violations raise `UnsafeArchiveError`, a `SourceSchemaError` with exit code 4.

### Local server

`lakehouse serve` binds loopback only (default `127.0.0.1:15080`) and serves a
generated static directory. It has no authentication and no TLS, and it refuses
non-loopback bind addresses. Do not expose it through a public interface or a
reverse proxy. Path traversal is rejected by the static handler.

### Artifact integrity

Published artifacts are self-verifying. `lakehouse verify DIR` checks
`SHA256SUMS`, parquet and DuckDB schemas and row counts, and the logical
`content_sha256` of every table, and exits 8 on any mismatch. The DuckDB file
contains only the public `marts` schema and a small `meta.build_info` table;
raw, staging and intermediate schemas are not published. Consumers should verify
an artifact once before using it.

### Data licensing

Only CC BY / CC BY 4.0 sources are bundled and published. Non-commercial BCE
datasets are excluded on purpose, so the artifact remains redistributable with
attribution. See [docs/DATA.md](docs/DATA.md) and
[docs/adr/0004-sample-strategy-and-licensing.md](docs/adr/0004-sample-strategy-and-licensing.md).

### Supply chain and CI

- `gitleaks` scans the full git history in CI; no secrets are stored in the
  repository or in fixtures.
- `pip-audit` audits the locked dependency export in CI. A known finding must be
  documented with a justification and a tracking note; it is never silently
  ignored.
- GitHub Actions are pinned by major version, use least-privilege `permissions`
  blocks, and the release workflow requires the full CI workflow to pass before
  it can create a release.
- The released wheel and sdist are built in CI from a locked environment.
- Dependabot monitors `github-actions` and `uv` weekly.

### Verification commands

```bash
uv run python scripts/dev.py check
uv lock --check
gitleaks detect --no-banner
uv export --no-hashes --no-emit-project > /tmp/requirements.txt
uvx pip-audit --disable-pip --no-deps -r /tmp/requirements.txt
```

If you believe any of these guarantees can be bypassed, report it privately
using the channel above.
