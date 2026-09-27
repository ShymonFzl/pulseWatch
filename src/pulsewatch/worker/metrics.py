"""Prometheus metrics of the worker, served on a dedicated port (ADR 0008)."""

import contextlib
import time
from collections.abc import Sequence
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

from pulsewatch.config import Settings
from pulsewatch.worker.prober import ProbeResult

PROBE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class WorkerMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.probes = Counter(
            "pulsewatch_probes_total",
            "Probes by result: ok, http_status or the error category.",
            ["result"],
            registry=registry,
        )
        self.probe_duration = Histogram(
            "pulsewatch_probe_duration_seconds",
            "Duration of probes, failures included.",
            buckets=PROBE_BUCKETS,
            registry=registry,
        )
        # Per-site series: labelled by id only, never by URL (bounded, no user text).
        self.site_up = Gauge(
            "pulsewatch_site_up",
            "Result of the last probe of each site (1 up, 0 down).",
            ["site_id"],
            registry=registry,
        )
        self.site_response_time = Gauge(
            "pulsewatch_site_response_time_seconds",
            "Response time of the last probe of each site that got a response.",
            ["site_id"],
            registry=registry,
        )
        self.ticks = Counter(
            "pulsewatch_worker_ticks_total",
            "Worker ticks by result.",
            ["result"],
            registry=registry,
        )
        self.tick_duration = Histogram(
            "pulsewatch_worker_tick_duration_seconds",
            "Duration of successful worker ticks.",
            registry=registry,
        )
        self.last_success = Gauge(
            "pulsewatch_worker_last_success_timestamp_seconds",
            "Unix time of the last successful tick; alert when it gets old.",
            registry=registry,
        )
        self._site_ids: set[str] = set()

    def record_probes(self, results: Sequence[tuple[int, ProbeResult]]) -> None:
        """Record one tick of probes; series of sites no longer probed are removed."""
        seen: set[str] = set()
        for site_id, result in results:
            label = str(site_id)
            seen.add(label)
            self.probes.labels(result.category).inc()
            self.probe_duration.observe(result.duration_seconds)
            self.site_up.labels(label).set(1 if result.ok else 0)
            if result.response_time_ms is not None:
                self.site_response_time.labels(label).set(result.response_time_ms / 1000)
            else:
                self._remove(self.site_response_time, label)
        for label in self._site_ids - seen:
            # Deleted site: drop its series instead of freezing its last value.
            self._remove(self.site_up, label)
            self._remove(self.site_response_time, label)
        self._site_ids = seen

    def record_tick_success(self, duration_seconds: float) -> None:
        self.ticks.labels("success").inc()
        self.tick_duration.observe(duration_seconds)
        self.last_success.set(time.time())

    def record_tick_failure(self) -> None:
        self.ticks.labels("failure").inc()

    @staticmethod
    def _remove(gauge: Gauge, label: str) -> None:
        with contextlib.suppress(KeyError):
            gauge.remove(label)


def start_metrics_server(settings: Settings, registry: CollectorRegistry) -> WSGIServer:
    """Serve /metrics in a background thread; call shutdown() to stop it."""
    server, _ = start_http_server(settings.metrics_port, settings.metrics_host, registry=registry)
    return server
