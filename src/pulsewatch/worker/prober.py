"""HTTP probe of a single site."""

import asyncio
import logging
import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2

import pulsewatch
from pulsewatch.worker.ssrf import (
    AddressPolicy,
    BlockedAddressError,
    DNSResolutionError,
    GuardedBackend,
    GuardedTransport,
    Resolver,
    is_public_address,
    system_resolver,
)

logger = logging.getLogger(__name__)

USER_AGENT = f"pulseWatch/{pulsewatch.__version__}"
MAX_REDIRECTS = 5
MAX_ERROR_LENGTH = 500


@dataclass(frozen=True, slots=True)
class ProbeResult:
    checked_at: datetime
    ok: bool
    status_code: int | None = None
    # Time until the final response headers, redirects included.
    response_time_ms: int | None = None
    error: str | None = None


def create_probe_client(
    timeout: float,
    *,
    policy: AddressPolicy = is_public_address,
    resolver: Resolver = system_resolver,
) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=GuardedTransport(GuardedBackend(policy, resolver)),
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        # Proxy environment variables must not bypass the SSRF guard.
        trust_env=False,
    )


def _error_category(exc: BaseException) -> str:
    # httpx2 wraps the transport errors: look at the whole cause chain.
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, BlockedAddressError):
            return "blocked_address"
        if isinstance(current, DNSResolutionError):
            return "dns_error"
        if isinstance(current, ssl.SSLError):
            return "tls_error"
        current = current.__cause__ or current.__context__
    if isinstance(exc, httpx2.ConnectError):
        return "connect_error"
    return "http_error"


def _error(category: str, detail: object = "") -> str:
    message = f"{category}: {detail}" if str(detail) else category
    return message[:MAX_ERROR_LENGTH]


# The probe owns its time budget so that it always returns a result.
async def probe(client: httpx2.AsyncClient, url: str, timeout: float) -> ProbeResult:  # noqa: ASYNC109
    """Probe a URL; never raises, failures are returned as results."""
    checked_at = datetime.now(UTC)
    started = time.perf_counter()
    try:
        # Total budget for the probe, redirects included.
        async with asyncio.timeout(timeout), client.stream("GET", url) as response:
            # Only the status and headers are read, never the body.
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            status_code = response.status_code
    except TimeoutError, httpx2.TimeoutException:
        return ProbeResult(
            checked_at, ok=False, error=_error("timeout", f"no response in {timeout}s")
        )
    except httpx2.TooManyRedirects as exc:
        return ProbeResult(checked_at, ok=False, error=_error("too_many_redirects", exc))
    except httpx2.RequestError as exc:
        return ProbeResult(checked_at, ok=False, error=_error(_error_category(exc), exc))
    except Exception as exc:
        # A single site must never crash the worker.
        logger.exception("Unexpected error while probing %s", url)
        return ProbeResult(
            checked_at, ok=False, error=_error("unexpected_error", type(exc).__name__)
        )
    return ProbeResult(
        checked_at,
        ok=200 <= status_code < 400,
        status_code=status_code,
        response_time_ms=elapsed_ms,
    )
