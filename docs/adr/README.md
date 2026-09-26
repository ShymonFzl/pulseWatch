# Architecture Decision Records

Each significant architecture or tooling decision is recorded here, using [0000-template.md](0000-template.md).
ADRs are numbered in order and never rewritten: a changed decision gets a new ADR that supersedes the old one.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-python-and-postgresql-versions.md) | Python 3.14 and PostgreSQL 17 | Accepted |
| [0002](0002-data-access-sqlalchemy-alembic.md) | Data access with SQLAlchemy 2 (async), Alembic and psycopg 3 | Accepted |
| [0003](0003-dependency-management-and-code-quality.md) | Dependency management with uv; code quality with Ruff and mypy | Accepted |
| [0004](0004-container-image.md) | One multi-stage Dockerfile, non-root, with pinned base images | Accepted |
| [0005](0005-worker-model.md) | Polling worker: a separate asyncio process | Accepted |
| [0006](0006-container-registry.md) | Container registry: build only in v0.1, Amazon ECR with OIDC in v0.2 | Accepted |
