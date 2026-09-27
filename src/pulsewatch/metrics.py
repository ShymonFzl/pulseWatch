"""Prometheus registry shared by the API and the worker (ADR 0008)."""

from prometheus_client import CollectorRegistry, GCCollector, PlatformCollector, ProcessCollector


def create_registry() -> CollectorRegistry:
    """One registry per process, with the standard process, platform and GC metrics.

    A dedicated registry (rather than the global one) lets tests build several
    apps without duplicate registrations.
    """
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)
    GCCollector(registry=registry)
    return registry
