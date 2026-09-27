# Tool versions

Single reference for the versions used by pulseWatch. Update this file in the same PR as any version change.
Python packages are pinned exactly in `uv.lock`. This table records the versions that matter for reviewing and reproducing the project.

## Runtime

| Component  | Version | Where it is pinned                              | Notes |
|------------|---------|-------------------------------------------------|-------|
| Python     | 3.14    | `.python-version`, `requires-python`             | Fallback to 3.13 if a dependency blocks |
| PostgreSQL | 17 (`postgres:17@sha256:d74eeac9…ec46f`) | `compose.yaml`, `test` job service in `.github/workflows/ci.yml` | Debian variant (glibc collations, like RDS). Dependabot updates `compose.yaml` only: align the CI digest by hand |

## Application libraries

| Library           | Version | Where it is pinned |
|-------------------|---------|--------------------|
| FastAPI           | 0.141.1 | `uv.lock`          |
| uvicorn           | 0.54.0  | `uv.lock`          |
| httpx2            | 2.13.1  | `uv.lock` (worker probes, ADR 0007; also the FastAPI test client) |
| SQLAlchemy        | 2.1.1   | `uv.lock`          |
| Alembic           | 1.20.0  | `uv.lock`          |
| psycopg           | 3.3.6   | `uv.lock`          |
| pydantic-settings | 2.15.0  | `uv.lock`          |

## Development tools

| Tool       | Version | Where it is pinned                              |
|------------|---------|-------------------------------------------------|
| uv         | 0.12.19 | `build-system` (`uv_build>=0.12,<0.13`), pre-commit `uv-lock` hook |
| Ruff       | 0.16.9  | `uv.lock`, pre-commit `ruff-pre-commit` hook     |
| mypy       | 2.3.1   | `uv.lock` (standard mode in v0.1, strict in v0.2) |
| pytest     | 9.1.1   | `uv.lock`                                        |
| pre-commit | 4.6.2   | `uv.lock`                                        |
| pre-commit-hooks | 6.0.0 | `.pre-commit-config.yaml`                  |

Keep the Ruff version in `.pre-commit-config.yaml` aligned with `uv.lock`.

## CI (GitHub Actions)

Actions are pinned by commit SHA in `.github/workflows/`, and Dependabot updates them.

| Component          | Version      |
|--------------------|--------------|
| Runner image       | ubuntu-24.04 |
| actions/checkout   | v7.0.1       |
| astral-sh/setup-uv | v10.2.0      |
