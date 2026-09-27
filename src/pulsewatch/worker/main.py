"""Worker loop: probe every site at a fixed rate and store the results.

Run with: python -m pulsewatch.worker
"""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Sequence

import httpx2
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    SmallInteger,
    Text,
    column,
    insert,
    select,
    values,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulsewatch.config import Settings
from pulsewatch.db.engine import create_engine, create_sessionmaker
from pulsewatch.db.models import Check, Site
from pulsewatch.metrics import create_registry
from pulsewatch.worker.metrics import WorkerMetrics, start_metrics_server
from pulsewatch.worker.prober import ProbeResult, create_probe_client, probe
from pulsewatch.worker.ssrf import AddressPolicy, is_public_address

logger = logging.getLogger(__name__)


async def save_results(
    sessionmaker: async_sessionmaker[AsyncSession], results: Sequence[tuple[int, ProbeResult]]
) -> int:
    """Insert the results in one statement; sites deleted meanwhile are skipped."""
    if not results:
        return 0
    rows = values(
        column("site_id", Integer),
        column("checked_at", DateTime(timezone=True)),
        column("ok", Boolean),
        column("status_code", SmallInteger),
        column("response_time_ms", Integer),
        column("error", Text),
        name="results",
    ).data(
        [
            (site_id, r.checked_at, r.ok, r.status_code, r.response_time_ms, r.error)
            for site_id, r in results
        ]
    )
    # The join drops rows whose site no longer exists, instead of failing the
    # whole batch on the foreign key.
    statement = (
        insert(Check)
        .from_select(
            ["site_id", "checked_at", "ok", "status_code", "response_time_ms", "error"],
            select(
                rows.c.site_id,
                rows.c.checked_at,
                rows.c.ok,
                rows.c.status_code,
                rows.c.response_time_ms,
                rows.c.error,
            ).join(Site, Site.id == rows.c.site_id),
        )
        .returning(Check.id)
    )
    async with sessionmaker() as session:
        saved = len((await session.scalars(statement)).all())
        await session.commit()
    return saved


async def run_tick(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: httpx2.AsyncClient,
    settings: Settings,
    metrics: WorkerMetrics | None = None,
) -> int:
    """Probe every site once and store the results. Returns the number of checks saved."""
    async with sessionmaker() as session:
        sites = (await session.execute(select(Site.id, Site.url).order_by(Site.id))).all()

    semaphore = asyncio.Semaphore(settings.probe_concurrency)

    async def probe_site(site_id: int, url: str) -> tuple[int, ProbeResult]:
        async with semaphore:
            return site_id, await probe(client, url, settings.probe_timeout_seconds)

    results = await asyncio.gather(*(probe_site(site.id, site.url) for site in sites))
    if metrics is not None:
        metrics.record_probes(results)
    return await save_results(sessionmaker, results)


async def run(
    settings: Settings,
    stop: asyncio.Event,
    *,
    policy: AddressPolicy = is_public_address,
    metrics: WorkerMetrics | None = None,
) -> None:
    """Run ticks at a fixed rate until stop is set."""
    loop = asyncio.get_running_loop()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    interval = settings.probe_interval_seconds
    try:
        async with create_probe_client(settings.probe_timeout_seconds, policy=policy) as client:
            logger.info("Worker started: interval=%ss", interval)
            next_tick = loop.time()
            while not stop.is_set():
                started = loop.time()
                try:
                    saved = await run_tick(sessionmaker, client, settings, metrics)
                except Exception:
                    # For example the database is down: log it and retry at the next tick.
                    logger.exception("Tick failed")
                    if metrics is not None:
                        metrics.record_tick_failure()
                else:
                    duration = loop.time() - started
                    logger.info("Tick done: %d checks in %.2fs", saved, duration)
                    if metrics is not None:
                        metrics.record_tick_success(duration)

                next_tick += interval
                if loop.time() > next_tick:
                    logger.warning("Tick overran the %ss interval", interval)
                    next_tick = loop.time()
                # Wait for the next tick, or return at once when stopping.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=next_tick - loop.time())
    finally:
        await engine.dispose()
        logger.info("Worker stopped")


async def _main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # The current tick finishes (bounded by the probe timeout), then the loop exits.
        loop.add_signal_handler(sig, stop.set)

    registry = create_registry()
    metrics_server = start_metrics_server(settings, registry)
    logger.info("Metrics on http://%s:%s/metrics", settings.metrics_host, settings.metrics_port)
    try:
        await run(settings, stop, metrics=WorkerMetrics(registry))
    finally:
        metrics_server.shutdown()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One INFO line per probe would flood the logs: results are stored in the database.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    asyncio.run(_main())
