"""Application settings, read from environment variables or a local .env file."""

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # e.g. postgresql+psycopg://user:password@localhost:5432/pulsewatch
    database_url: PostgresDsn
