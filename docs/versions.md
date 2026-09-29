# Tool versions

Single reference for the versions used by pulseWatch. Update this file in the same PR as any version change.
Python packages are pinned exactly in `uv.lock`. This table records the versions that matter for reviewing and reproducing the project.

## Runtime

| Component  | Version | Where it is pinned                              | Notes |
|------------|---------|-------------------------------------------------|-------|
| Python     | 3.14    | `.python-version`, `requires-python`             | Fallback to 3.13 if a dependency blocks |
| Python base image | `python:3.14-slim-trixie@sha256:51dafde8…5b3d` | `Dockerfile` (`builder` and `runtime` stages) | Updated by Dependabot (`docker`) |
| uv image | `ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b1…f424` | `Dockerfile` (`uv` stage) | Keep aligned with the local uv version |
| PostgreSQL | 17 (`postgres:17@sha256:d74eeac9…ec46f`) | `compose.yaml`, `test` job service in `.github/workflows/ci.yml` | Debian variant (glibc collations, like RDS). Dependabot updates `compose.yaml` only: align the CI digest by hand |

## Application libraries

| Library           | Version | Where it is pinned |
|-------------------|---------|--------------------|
| FastAPI           | 0.141.1 | `uv.lock`          |
| uvicorn           | 0.54.0  | `uv.lock`          |
| httpx2            | 2.13.1  | `uv.lock` (worker probes, ADR 0007; also the FastAPI test client) |
| prometheus-client | 0.26.0  | `uv.lock` (ADR 0008) |
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
| docker/setup-buildx-action | v4.4.1 |
| docker/build-push-action   | v7.4.0 |
| github/codeql-action (upload-sarif) | v4.38.2 |
| actions/cache      | v6.1.0       |

## Container tooling

| Tool     | Version | Use |
|----------|---------|-----|
| hadolint | v2.15.1 (`hadolint/hadolint:v2.15.1@sha256:32dac941…a12d`) | Dockerfile lint (CI job `container-config`) |
| Trivy    | 0.74.0 (`aquasec/trivy:0.74.0@sha256:62b1e65e…1969`)       | Image scan (CI job `image`) and Dockerfile config scan (`container-config`) |

CI runs both tools from their official images, pinned by digest in `.github/workflows/ci.yml`. Dependabot does not update image references inside workflow steps: bump these digests by hand, together with this table.
