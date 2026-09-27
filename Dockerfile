# pulseWatch images (ADR 0004): one Dockerfile, two targets.
#   docker build --target api    -t pulsewatch-api .
#   docker build --target worker -t pulsewatch-worker .
# Every base image is pinned by digest; Dependabot updates the digests.

# Only used as the source of the uv binary, same version as local development.
FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv

# --- builder: resolves and installs everything into /app/.venv -------------
FROM python:3.14-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS builder

COPY --from=uv /uv /usr/local/bin/uv

# Compile bytecode at build time (the runtime writes nothing), copy instead of
# hard-linking from the cache mount, and use the image's Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first: this layer is reused until uv.lock or pyproject.toml change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# Then the project itself, installed as a regular package: the runtime needs no src/.
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- runtime: common base of the final images, no build tools --------------
FROM python:3.14-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime

LABEL org.opencontainers.image.title="pulseWatch" \
      org.opencontainers.image.source="https://github.com/ShymonFzl/pulseWatch" \
      org.opencontainers.image.licenses="MIT"

# pip is not needed at runtime (the venv is built by uv) and vendors packages
# with known vulnerabilities: remove it to shrink the attack surface.
RUN python -m pip uninstall --yes --no-cache-dir pip \
    && groupadd --system --gid 10001 pulsewatch \
    && useradd --system --uid 10001 --gid 10001 --no-create-home \
       --shell /usr/sbin/nologin pulsewatch

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Owned by root and not writable by the app user: the installed code is immutable.
COPY --from=builder /app/.venv /app/.venv
# Migrations, for the one-shot migrate job: alembic upgrade head.
COPY alembic.ini ./
COPY migrations/ migrations/

USER 10001:10001

# --- api --------------------------------------------------------------------
FROM runtime AS api

LABEL org.opencontainers.image.title="pulseWatch API"

EXPOSE 8000

# Liveness only; readiness (/health/ready) is left to the orchestrator.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "--factory", "pulsewatch.api.main:create_app", "--host", "0.0.0.0", "--port", "8000"]

# --- worker -----------------------------------------------------------------
FROM runtime AS worker

LABEL org.opencontainers.image.title="pulseWatch worker"

# Inside a container the metrics server must listen on all interfaces (ADR 0008).
ENV METRICS_HOST=0.0.0.0

EXPOSE 9100

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9100/metrics', timeout=2)"]

CMD ["python", "-m", "pulsewatch.worker"]
