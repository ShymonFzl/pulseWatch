"""FastAPI application factory.

Run with: uvicorn --factory pulsewatch.api.main:create_app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import pulsewatch
from pulsewatch.api.routes import health, sites
from pulsewatch.config import Settings
from pulsewatch.db.engine import create_engine, create_sessionmaker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="pulseWatch", version=pulsewatch.__version__, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(sites.router)
    return app
