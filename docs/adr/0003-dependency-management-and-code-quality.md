# 0003. Dependency management with uv; code quality with Ruff and mypy

- Status: Accepted
- Date: 2026-09-26

## Context

Builds must be reproducible on laptops, in CI and in Docker images. Every change must pass the same lint, format, type and test checks, locally before committing and in CI.

## Decision

- **uv** manages the Python version, the virtual environment and dependencies. Dependencies are declared in `pyproject.toml` and pinned in a committed `uv.lock`. CI installs with `uv sync --locked`, which fails if `uv.lock` is out of date with `pyproject.toml`. Docker builds use `uv sync --frozen`, which installs exactly what the lockfile says without re-resolving; the lockfile has already been checked by CI.
- **Ruff** is the only linter and formatter (it replaces flake8, isort and black). The rule set includes bugbear, pyupgrade and the bandit security rules (`S`).
- **mypy** checks `src/` and `tests/`: **standard mode in v0.1** (with `check_untyped_defs` and unused-ignore warnings), **strict mode in v0.2**.
- **pytest** runs the tests.
- **pre-commit** runs these checks locally, with pinned hook revisions. CI runs the same commands and is the source of truth.

## Alternatives considered

- **Poetry**: mature, but slower and heavier in CI and Docker images, and it does not manage Python versions.
- **pip-tools**: minimal, but needs separate tools for virtual environments and Python versions.
- **flake8 + isort + black**: three tools and three configurations for what Ruff does alone, and faster.
- **Strict mypy from the start**: stronger guarantees, but more friction while the codebase and its third-party stubs settle. We defer it to v0.2.
- **pyright or ty**: pyright is a good alternative. ty is still young. mypy has the most mature support for Pydantic and SQLAlchemy.

## Consequences

- Fast, deterministic installs, and a lockfile that Dependabot can update.
- Tool versions are recorded in `docs/versions.md`. The Ruff version in pre-commit must stay aligned with `uv.lock`.
- Moving to strict mypy in v0.2 is a planned piece of work (its own issue), not a surprise.
