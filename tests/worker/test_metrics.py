import urllib.request
from datetime import UTC, datetime

from prometheus_client import CollectorRegistry

from pulsewatch.config import Settings
from pulsewatch.metrics import create_registry
from pulsewatch.worker.metrics import WorkerMetrics, start_metrics_server
from pulsewatch.worker.prober import ProbeResult
from tests.worker.fake_site import free_port

NOW = datetime.now(UTC)
UP = ProbeResult(NOW, ok=True, status_code=200, response_time_ms=120, duration_seconds=0.12)
DOWN = ProbeResult(
    NOW,
    ok=False,
    status_code=500,
    response_time_ms=80,
    category="http_status",
    duration_seconds=0.08,
)
BLOCKED = ProbeResult(
    NOW, ok=False, error="blocked_address: ...", category="blocked_address", duration_seconds=0.001
)


def value(registry: CollectorRegistry, name: str, **labels: str) -> float | None:
    return registry.get_sample_value(name, labels)


def test_probe_results_are_recorded() -> None:
    registry = CollectorRegistry()
    metrics = WorkerMetrics(registry)

    metrics.record_probes([(1, UP), (2, DOWN), (3, BLOCKED)])

    assert value(registry, "pulsewatch_probes_total", result="ok") == 1
    assert value(registry, "pulsewatch_probes_total", result="http_status") == 1
    assert value(registry, "pulsewatch_probes_total", result="blocked_address") == 1
    assert value(registry, "pulsewatch_probe_duration_seconds_count") == 3
    assert value(registry, "pulsewatch_site_up", site_id="1") == 1
    assert value(registry, "pulsewatch_site_up", site_id="2") == 0
    assert value(registry, "pulsewatch_site_up", site_id="3") == 0
    assert value(registry, "pulsewatch_site_response_time_seconds", site_id="1") == 0.12
    # No response, so no response time.
    assert value(registry, "pulsewatch_site_response_time_seconds", site_id="3") is None


def test_series_of_deleted_sites_are_removed() -> None:
    registry = CollectorRegistry()
    metrics = WorkerMetrics(registry)
    metrics.record_probes([(1, UP), (2, DOWN)])

    metrics.record_probes([(1, UP)])

    assert value(registry, "pulsewatch_site_up", site_id="1") == 1
    assert value(registry, "pulsewatch_site_up", site_id="2") is None
    assert value(registry, "pulsewatch_site_response_time_seconds", site_id="2") is None


def test_ticks_are_recorded() -> None:
    registry = CollectorRegistry()
    metrics = WorkerMetrics(registry)

    metrics.record_tick_success(0.5)
    metrics.record_tick_failure()

    assert value(registry, "pulsewatch_worker_ticks_total", result="success") == 1
    assert value(registry, "pulsewatch_worker_ticks_total", result="failure") == 1
    assert value(registry, "pulsewatch_worker_tick_duration_seconds_count") == 1
    last_success = value(registry, "pulsewatch_worker_last_success_timestamp_seconds")
    assert last_success is not None
    assert last_success > 0


def test_metrics_server_serves_the_registry() -> None:
    port = free_port()
    settings = Settings.model_validate(
        {"database_url": "postgresql+psycopg://u:p@127.0.0.1:1/none", "metrics_port": port}
    )
    registry = create_registry()
    WorkerMetrics(registry).record_probes([(7, UP)])

    server = start_metrics_server(settings, registry)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
            body = response.read().decode()
    finally:
        server.shutdown()
        server.server_close()

    assert 'pulsewatch_site_up{site_id="7"} 1.0' in body
    assert 'pulsewatch_probes_total{result="ok"} 1.0' in body
    assert "process_cpu_seconds_total" in body
