import ipaddress
from collections.abc import Iterable
from typing import cast

import httpcore2
import pytest

from pulsewatch.worker.ssrf import (
    BlockedAddressError,
    GuardedBackend,
    is_public_address,
    system_resolver,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "10.1.2.3",  # private
        "172.16.0.1",  # private
        "192.168.1.1",  # private
        "169.254.169.254",  # link-local: cloud metadata service
        "100.64.0.1",  # CGNAT
        "0.0.0.0",  # noqa: S104 (unspecified address, rejected)
        "224.0.0.1",  # multicast
        "::1",  # loopback
        "::",  # unspecified
        "fe80::1",  # link-local
        "fc00::1",  # unique local
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",  # IPv4-mapped metadata service
        "64:ff9b::a9fe:a9fe",  # NAT64 form of 169.254.169.254
    ],
)
def test_non_public_addresses_are_rejected(address: str) -> None:
    assert not is_public_address(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "2606:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address))


class RecordingBackend(httpcore2.AsyncNetworkBackend):
    """Records connection attempts instead of opening sockets."""

    def __init__(self) -> None:
        self.connected_to: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore2 interface)
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.connected_to.append(host)
        return cast(httpcore2.AsyncNetworkStream, object())


class FakeResolver:
    def __init__(self, *answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls = 0

    async def __call__(self, host: str, port: int) -> list[str]:
        self.calls += 1
        return self.answers.pop(0)


async def test_host_resolving_to_private_address_is_blocked() -> None:
    delegate = RecordingBackend()
    backend = GuardedBackend(resolver=FakeResolver(["10.0.0.5"]), delegate=delegate)

    with pytest.raises(BlockedAddressError, match=r"10\.0\.0\.5"):
        await backend.connect_tcp("internal.example.com", 80)
    assert delegate.connected_to == []


async def test_one_private_address_blocks_the_host() -> None:
    delegate = RecordingBackend()
    resolver = FakeResolver(["93.184.216.34", "169.254.169.254"])
    backend = GuardedBackend(resolver=resolver, delegate=delegate)

    with pytest.raises(BlockedAddressError):
        await backend.connect_tcp("mixed.example.com", 80)
    assert delegate.connected_to == []


async def test_connects_to_the_validated_address_without_resolving_again() -> None:
    # DNS rebinding: the second answer points to the metadata service.
    delegate = RecordingBackend()
    resolver = FakeResolver(["93.184.216.34"], ["169.254.169.254"])
    backend = GuardedBackend(resolver=resolver, delegate=delegate)

    await backend.connect_tcp("rebind.example.com", 443)

    assert delegate.connected_to == ["93.184.216.34"]
    assert resolver.calls == 1

    # A new connection is validated again, with the new answer.
    with pytest.raises(BlockedAddressError):
        await backend.connect_tcp("rebind.example.com", 443)
    assert delegate.connected_to == ["93.184.216.34"]


async def test_ip_literals_are_checked_without_resolution() -> None:
    delegate = RecordingBackend()
    resolver = FakeResolver()
    backend = GuardedBackend(resolver=resolver, delegate=delegate)

    with pytest.raises(BlockedAddressError):
        await backend.connect_tcp("169.254.169.254", 80)
    assert resolver.calls == 0
    assert delegate.connected_to == []


async def test_unix_sockets_are_blocked() -> None:
    with pytest.raises(BlockedAddressError):
        await GuardedBackend(delegate=RecordingBackend()).connect_unix_socket("/var/run/x.sock")


async def test_localhost_resolves_to_a_blocked_address() -> None:
    addresses = await system_resolver("localhost", 80)

    assert addresses
    assert not any(is_public_address(ipaddress.ip_address(a)) for a in addresses)
