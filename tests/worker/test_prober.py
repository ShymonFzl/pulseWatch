import ipaddress
import socket

import pytest

from pulsewatch.worker.prober import create_probe_client, probe
from pulsewatch.worker.ssrf import DNSResolutionError, IPAddress
from tests.worker.fake_site import FakeSite

pytestmark = pytest.mark.anyio

TIMEOUT = 1.0


def allow_only_127_0_0_1(address: IPAddress) -> bool:
    # Test policy: the fake site on 127.0.0.1 is reachable, every other address is not.
    return address == ipaddress.ip_address("127.0.0.1")


async def test_success(fake_site: FakeSite) -> None:
    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, fake_site.url("/ok"), TIMEOUT)

    assert result.ok
    assert result.status_code == 200
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0
    assert result.error is None


async def test_server_error_is_not_ok(fake_site: FakeSite) -> None:
    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, fake_site.url("/error"), TIMEOUT)

    assert not result.ok
    assert result.status_code == 500
    assert result.error is None


async def test_slow_server_times_out(fake_site: FakeSite) -> None:
    async with create_probe_client(0.5, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, fake_site.url("/slow"), 0.5)

    assert not result.ok
    assert result.status_code is None
    assert result.error is not None
    assert result.error.startswith("timeout")


async def test_dns_failure() -> None:
    async def failing_resolver(host: str, port: int) -> list[str]:
        raise DNSResolutionError(f"cannot resolve {host}")

    async with create_probe_client(
        TIMEOUT, policy=allow_only_127_0_0_1, resolver=failing_resolver
    ) as client:
        result = await probe(client, "http://does-not-exist.invalid/", TIMEOUT)

    assert not result.ok
    assert result.error is not None
    assert result.error.startswith("dns_error")


async def test_connection_refused() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Nothing listens on this port any more.

    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, f"http://127.0.0.1:{port}/", TIMEOUT)

    assert not result.ok
    assert result.error is not None
    assert result.error.startswith("connect_error")


async def test_allowed_redirect_is_followed(fake_site: FakeSite) -> None:
    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, fake_site.url("/redirect?to=/ok"), TIMEOUT)

    assert result.ok
    assert result.status_code == 200
    assert fake_site.requests == ["/redirect?to=/ok", "/ok"]


@pytest.mark.parametrize(
    "target",
    ["http://127.0.0.2:{port}/ok", "http://169.254.169.254/latest/meta-data/"],
)
async def test_redirect_to_blocked_address_is_refused(fake_site: FakeSite, target: str) -> None:
    url = fake_site.url(f"/redirect?to={target.format(port=fake_site.port)}")

    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, url, TIMEOUT)

    assert not result.ok
    assert result.error is not None
    assert result.error.startswith("blocked_address")


async def test_too_many_redirects(fake_site: FakeSite) -> None:
    async with create_probe_client(TIMEOUT, policy=allow_only_127_0_0_1) as client:
        result = await probe(client, fake_site.url("/loop"), TIMEOUT)

    assert not result.ok
    assert result.error is not None
    assert result.error.startswith("too_many_redirects")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:{port}/ok",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:{port}/ok",
        "http://localhost:{port}/ok",
    ],
)
async def test_real_policy_blocks_internal_targets(fake_site: FakeSite, url: str) -> None:
    # Production policy: the fake site is up, yet it must never be reached.
    async with create_probe_client(TIMEOUT) as client:
        result = await probe(client, url.format(port=fake_site.port), TIMEOUT)

    assert not result.ok
    assert result.status_code is None
    assert result.error is not None
    assert result.error.startswith("blocked_address")
    assert fake_site.requests == []
