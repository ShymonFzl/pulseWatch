import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy import URL, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pulsewatch.config import Settings
from pulsewatch.db.engine import create_engine as create_async_engine
from pulsewatch.db.engine import create_sessionmaker
from pulsewatch.worker.main import run_tick, save_results
from pulsewatch.worker.metrics import WorkerMetrics
from pulsewatch.worker.prober import ProbeResult, create_probe_client
from tests.worker.fake_site import FakeSite, free_port
from tests.worker.test_prober import allow_only_127_0_0_1

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
def settings(migrated_database_url: URL) -> Settings:
    engine = create_engine(migrated_database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sites, checks RESTART IDENTITY"))
    engine.dispose()
    url = migrated_database_url.render_as_string(hide_password=False)
    return Settings.model_validate({"database_url": url, "probe_timeout_seconds": 1})


@pytest.fixture
async def sessionmaker(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings)
    yield create_sessionmaker(engine)
    await engine.dispose()


async def add_site(sessionmaker: async_sessionmaker[AsyncSession], name: str, url: str) -> int:
    async with sessionmaker() as session:
        site_id: int = (
            await session.execute(
                text("INSERT INTO sites (name, url) VALUES (:name, :url) RETURNING id"),
                {"name": name, "url": url},
            )
        ).scalar_one()
        await session.commit()
    return site_id


async def test_tick_stores_one_check_per_site(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], fake_site: FakeSite
) -> None:
    up = await add_site(sessionmaker, "up", fake_site.url("/ok"))
    down = await add_site(sessionmaker, "down", fake_site.url("/error"))
    metadata = await add_site(sessionmaker, "metadata", "http://169.254.169.254/latest/meta-data/")

    async with create_probe_client(1, policy=allow_only_127_0_0_1) as client:
        saved = await run_tick(sessionmaker, client, settings)

    assert saved == 3
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                text("SELECT site_id, ok, status_code, error FROM checks ORDER BY site_id")
            )
        ).all()
    by_site = {row.site_id: row for row in rows}
    assert (by_site[up].ok, by_site[up].status_code, by_site[up].error) == (True, 200, None)
    assert (by_site[down].ok, by_site[down].status_code) == (False, 500)
    assert by_site[metadata].ok is False
    assert by_site[metadata].status_code is None
    assert by_site[metadata].error.startswith("blocked_address")


async def test_tick_updates_metrics(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], fake_site: FakeSite
) -> None:
    up = await add_site(sessionmaker, "up", fake_site.url("/ok"))
    down = await add_site(sessionmaker, "down", fake_site.url("/error"))
    registry = CollectorRegistry()

    async with create_probe_client(1, policy=allow_only_127_0_0_1) as client:
        await run_tick(sessionmaker, client, settings, WorkerMetrics(registry))

    assert registry.get_sample_value("pulsewatch_site_up", {"site_id": str(up)}) == 1
    assert registry.get_sample_value("pulsewatch_site_up", {"site_id": str(down)}) == 0
    assert registry.get_sample_value("pulsewatch_probes_total", {"result": "ok"}) == 1
    assert registry.get_sample_value("pulsewatch_probes_total", {"result": "http_status"}) == 1


async def test_results_of_deleted_sites_are_skipped(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    kept = await add_site(sessionmaker, "kept", "https://kept.example.com/")
    now = datetime.now(UTC)
    results = [
        (kept, ProbeResult(now, ok=True, status_code=200, response_time_ms=12)),
        # This site was deleted while the tick was running.
        (999_999, ProbeResult(now, ok=True, status_code=200, response_time_ms=34)),
    ]

    saved = await save_results(sessionmaker, results)

    assert saved == 1
    async with sessionmaker() as session:
        result = await session.execute(text("SELECT site_id FROM checks"))
        site_ids: list[int] = list(result.scalars())
    assert site_ids == [kept]


def test_worker_serves_metrics_and_stops_cleanly_on_sigterm(
    settings: Settings, tmp_path: Path
) -> None:
    metrics_port = free_port()
    env = {
        **os.environ,
        "DATABASE_URL": str(settings.database_url),
        "PROBE_INTERVAL_SECONDS": "5",
        "METRICS_PORT": str(metrics_port),
    }
    # cwd=tmp_path: no local .env is read.
    process = subprocess.Popen(
        [sys.executable, "-m", "pulsewatch.worker"],
        env=env,
        cwd=tmp_path,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    assert process.stderr is not None
    stderr = process.stderr

    def pump() -> None:
        for line in stderr:
            lines.put(line)

    threading.Thread(target=pump, daemon=True).start()

    def wait_for(message: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if message in lines.get(timeout=0.1):
                    return
            except queue.Empty:
                continue
        pytest.fail(f"worker did not log {message!r} within {timeout}s")

    try:
        wait_for("Tick done", timeout=15)
        metrics_url = f"http://127.0.0.1:{metrics_port}/metrics"
        with urllib.request.urlopen(metrics_url, timeout=5) as response:
            body = response.read().decode()
        assert 'pulsewatch_worker_ticks_total{result="success"}' in body

        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=15) == 0
        wait_for("Worker stopped", timeout=1)
    finally:
        if process.poll() is None:
            process.kill()
