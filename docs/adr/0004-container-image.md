# 0004. One multi-stage Dockerfile, non-root, with pinned base images

- Status: Accepted
- Date: 2026-09-26

## Context

The API and the worker come from the same Python package. Their images must be small, reproducible, free of build tooling, and must not run as root. They will be scanned by Trivy in CI and later deployed on Kubernetes.

## Decision

- **One `Dockerfile`** with several stages:
  - `builder`: installs dependencies with uv (`uv sync --frozen --no-dev`) into `/app/.venv`.
  - `runtime`: `python:3.14-slim`, containing only the virtual environment and the application code.
  - two final targets, **`api`** and **`worker`**, that differ only in their command, exposed port and healthcheck.
- The process runs as a **dedicated non-root user (UID 10001)**, with no build tools or package manager caches in the final image.
- Every base image is **pinned by digest** (`image:tag@sha256:...`). Dependabot updates the digests.
- A `.dockerignore` keeps the build context minimal (no `.git`, `.venv`, caches or local `.env`).

## Alternatives considered

- **Two separate Dockerfiles**: they duplicate the dependency stage and drift over time.
- **Distroless or other minimal base images**: fewer packages and CVEs, but no shell, which makes debugging harder at this stage. To revisit once the platform is stable.
- **Single-stage image**: simpler, but it ships compilers, uv and caches, which means a larger attack surface and more CVEs.

## Consequences

- Two thin images built from one source of truth, sharing cached layers.
- Reproducible builds. Base image updates are explicit, reviewable PRs.
- Non-root by default, which already satisfies the future Kubernetes `runAsNonRoot` and restricted Pod Security settings.
