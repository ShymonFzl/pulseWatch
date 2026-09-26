"""Async engine factory shared by the API and the worker."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pulsewatch.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # Lazy: no connection is opened until the first query.
    return create_async_engine(str(settings.database_url), pool_pre_ping=True)
