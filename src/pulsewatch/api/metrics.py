"""HTTP metrics of the API (ADR 0008)."""

import time

from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Requests that match no route share one label value, so arbitrary URLs cannot
# create new series.
UNMATCHED_ROUTE = "unmatched"


class ApiMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.requests = Counter(
            "pulsewatch_http_requests_total",
            "HTTP requests handled by the API.",
            ["method", "route", "status"],
            registry=registry,
        )
        self.duration = Histogram(
            "pulsewatch_http_request_duration_seconds",
            "Duration of HTTP requests handled by the API.",
            ["method", "route"],
            registry=registry,
        )


class MetricsMiddleware:
    """Pure ASGI middleware: counts requests and measures their duration."""

    def __init__(self, app: ASGIApp, metrics: ApiMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = 500  # If the app raises before responding.
        started = time.perf_counter()

        async def send_and_record_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_record_status)
        finally:
            # The router stores the matched route in the scope: use its
            # template (/sites/{site_id}), never the raw path.
            route = scope.get("route")
            route_label = getattr(route, "path", UNMATCHED_ROUTE)
            method = scope["method"]
            self.metrics.requests.labels(method, route_label, str(status)).inc()
            self.metrics.duration.labels(method, route_label).observe(time.perf_counter() - started)
