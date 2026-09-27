"""Application settings, read from environment variables or a local .env file."""

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # e.g. postgresql+psycopg://user:password@localhost:5432/pulsewatch
    database_url: PostgresDsn

    # Worker (ADR 0005)
    probe_interval_seconds: float = Field(default=60, ge=5)
    # Total budget of one probe, redirects included.
    probe_timeout_seconds: float = Field(default=10, gt=0, le=60)
    probe_concurrency: int = Field(default=20, ge=1, le=200)

    # Prometheus metrics of the worker, on a dedicated port. Local default:
    # loopback only; containers set METRICS_HOST=0.0.0.0.
    metrics_host: str = "127.0.0.1"
    metrics_port: int = Field(default=9100, ge=1, le=65535)
