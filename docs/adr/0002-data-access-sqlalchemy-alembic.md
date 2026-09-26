# 0002. Data access with SQLAlchemy 2 (async), Alembic and psycopg 3

- Status: Accepted
- Date: 2026-09-26

## Context

The API and the worker share two tables (`sites`, `checks`). Both are asyncio applications. The schema will change over time and must be migrated reliably in local, CI and deployed environments, without hand-written ad hoc SQL scripts.

## Decision

- **SQLAlchemy 2.x** with its asyncio extension. Models are declared with typed `Mapped[...]` annotations and shared by the API and the worker.
- **Alembic** for schema migrations. Every schema change ships as a versioned, reversible migration (`upgrade` and `downgrade`).
- **psycopg 3** as the only PostgreSQL driver. It supports both async (application) and sync (Alembic) usage.
- Migrations run as a separate one-shot step (a `migrate` service in compose, a Kubernetes Job later), never on application startup.
- Tests run against a real PostgreSQL, not SQLite or mocks.

## Alternatives considered

- **Raw SQL with asyncpg**: fast and explicit, but provides no migration tooling or typed models, so we would rebuild both by hand.
- **SQLModel**: a thinner API on top of SQLAlchemy and Pydantic, but an extra layer that is less mature, with fewer features for migrations and complex queries.
- **asyncpg as the driver**: async only. Alembic would need a second, synchronous driver.

## Consequences

- Typed queries that mypy can check, and one well-documented ecosystem.
- Migrations are reviewable in PRs and run before the new code starts, which avoids races between replicas.
- Contributors need to know the SQLAlchemy 2.0 style (`select()`, `AsyncSession`), not the legacy `Query` API.
