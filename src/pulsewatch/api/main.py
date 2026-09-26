"""FastAPI application factory.

Run with: uvicorn --factory pulsewatch.api.main:create_app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import pulsewatch
from pulsewatch.api.routes import health
from pulsewatch.config import Settings
from pulsewatch.db.engine import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="pulseWatch", version=pulsewatch.__version__, lifespan=lifespan)
    app.include_router(health.router)
    return app
