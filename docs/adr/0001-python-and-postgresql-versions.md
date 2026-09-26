# 0001. Python 3.14 and PostgreSQL 17

- Status: Accepted
- Date: 2026-09-26

## Context

pulseWatch v0.1 is a FastAPI API and a polling worker backed by PostgreSQL. It will later run on AWS (Amazon RDS for the database, Kubernetes for the workloads). We need a language runtime and a database major version that the whole stack supports and that stay supported for the life of the project.

## Decision

- **Python 3.14**, pinned in `.python-version` and `requires-python`. If a required dependency does not support 3.14, we fall back to **Python 3.13** and record that change in a new ADR.
- **PostgreSQL 17**, used in the same major version locally (docker compose), in CI (service container) and in the managed database later.

## Alternatives considered

- **Python 3.13**: the most conservative choice, kept as the fallback. 3.14 is stable, supported by the libraries we use, and gives the longest support window.
- **PostgreSQL 18**: the newest major version. We chose 17 for its maturity and its broad availability on managed services, so local, CI and production can run the same major version from day one.

## Consequences

- One Python and one PostgreSQL major version everywhere, recorded in `docs/versions.md`.
- A later move to PostgreSQL 18 is a planned major upgrade (`pg_upgrade` or a managed upgrade), made in a dedicated change with its own ADR.
- If we fall back to Python 3.13, we update `.python-version`, `requires-python`, the Ruff and mypy target versions and the base image together.
