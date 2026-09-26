"""Async engine and session factories shared by the API and the worker."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pulsewatch.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # Lazy: no connection is opened until the first query.
    return create_async_engine(str(settings.database_url), pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
