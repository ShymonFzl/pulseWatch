"""Liveness and readiness probes."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

READINESS_TIMEOUT_SECONDS = 2.0


class HealthStatus(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get("")
async def liveness() -> HealthStatus:
    # Never depends on the database: a DB outage must not restart healthy processes.
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthStatus}},
)
async def readiness(request: Request, response: Response) -> HealthStatus:
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        # Details go to the logs, never to the client.
        logger.exception("Readiness check failed: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="unavailable")
    return HealthStatus(status="ok")
