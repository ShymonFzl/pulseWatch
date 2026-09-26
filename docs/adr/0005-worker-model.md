# 0005. Polling worker: a separate asyncio process

- Status: Accepted
- Date: 2026-09-26

## Context

pulseWatch must check each monitored site at a regular interval and store the result. The probes are I/O bound: HTTP requests that may be slow or time out. v0.1 targets a modest number of sites and must stay simple to run locally and to deploy later.

## Decision

- The worker is a **separate process** (its own container), independent of the API. The two share only the database and the `pulsewatch` package.
- It runs an **asyncio loop**. On each tick it loads the sites and probes them concurrently with **httpx**, with a per-request timeout and a **semaphore bounding concurrency**.
- **Global interval**, configurable (default 60 s). The `sites.interval_seconds` column exists but is not exposed or used in v0.1.
- **A single replica in v0.1.** Scaling out will use `SELECT ... FOR UPDATE SKIP LOCKED` to share work between replicas, recorded in a future ADR.
- Clean shutdown on SIGTERM: stop scheduling new probes and let in-flight probes finish within a grace period.
- Protection against SSRF (probing internal addresses) is decided in a dedicated ADR, as part of issue #9.

## Alternatives considered

- **Celery or RQ with Redis**: a queue and a broker to operate and monitor, which v0.1 does not need.
- **APScheduler**: adds a dependency for little gain over a plain asyncio loop at this scale.
- **Background task inside the API process**: couples probe load to API latency and prevents scaling the two independently.

## Consequences

- No infrastructure beyond PostgreSQL. The worker is easy to reason about and to test.
- Running more than one replica before the `SKIP LOCKED` change would probe every site twice, so the deployment must keep `replicas: 1` until then.
- Per-site intervals and scaling out are planned work, not rewrites.
