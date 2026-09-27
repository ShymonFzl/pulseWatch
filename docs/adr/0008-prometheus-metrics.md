# 0008. Prometheus metrics

- Status: Accepted
- Date: 2026-09-27

## Context

pulseWatch must be observable once deployed: request rate, errors and latency of the API; activity and health of the worker; and the status of each monitored site. Prometheus is the target monitoring system (Grafana dashboards and alerts come later). The API and the worker run as separate processes, one process per container (ADR 0005).

## Decision

- **Library**: the official `prometheus-client`, in single-process mode (one process per container, so no multiprocess mode).
- **One registry per process**, created by `pulsewatch.metrics.create_registry()`, with the standard process, platform and GC collectors. The global default registry is not used, so tests can build several apps without duplicate registrations.
- **API**: `GET /metrics` on the API port, excluded from the OpenAPI schema. A pure ASGI middleware records `pulsewatch_http_requests_total{method, route, status}` and `pulsewatch_http_request_duration_seconds{method, route}`.
- **Worker**: a dedicated metrics port (`metrics_port`, default 9100) served by `prometheus-client`'s HTTP server. It exposes:
  - `pulsewatch_probes_total{result}` (`ok`, `http_status` or the error category) and `pulsewatch_probe_duration_seconds`;
  - `pulsewatch_site_up{site_id}` and `pulsewatch_site_response_time_seconds{site_id}`, for the last result of each site;
  - `pulsewatch_worker_ticks_total{result}`, `pulsewatch_worker_tick_duration_seconds` and `pulsewatch_worker_last_success_timestamp_seconds`, so an alert can detect a stuck worker.
- **Naming**: the `pulsewatch_` prefix, base units (seconds), and `_total` for counters.
- **Bounded cardinality**:
  - the API labels routes by their template (`/sites/{site_id}`), and every request that matches no route by `unmatched`;
  - per-site series are labelled by `site_id` only, never by URL (user-supplied, unbounded text);
  - the series of a deleted site are removed at the next tick.
- **Exposure**:
  - the worker's metrics server listens on `127.0.0.1` by default; containers set `METRICS_HOST=0.0.0.0`;
  - `/metrics` has no authentication in v0.1, so the ingress must not route it publicly. Prometheus scrapes it inside the cluster.

## Alternatives considered

- **prometheus-fastapi-instrumentator**: an extra dependency for what a 40-line middleware does, with less control over labels.
- **OpenTelemetry metrics**: more general (traces, several backends), but heavier. To be considered with tracing in the observability phase.
- **Worker metrics served through the API**: this would couple the two processes, and the API cannot see the worker's in-memory state.
- **Labelling sites by URL**: easier to read, but unbounded and user-controlled. Dashboards can join `site_id` with the API data.

## Consequences

- Scrape targets: the API port and the worker's metrics port. The Kubernetes manifests will need a scrape configuration for both, and an ingress that excludes `/metrics`.
- Per-site series grow with the number of sites. This is acceptable in v0.1; if sites number in the thousands, per-site gauges should move to recording rules or be dropped in favour of the database.
