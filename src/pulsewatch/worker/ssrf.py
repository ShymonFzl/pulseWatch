"""SSRF protection for outgoing probes (ADR 0007).

Every new TCP connection goes through GuardedBackend: it resolves the host
itself, rejects the connection if any resolved address is not public, and
connects to a validated address without resolving again. This defeats DNS
rebinding, and redirects are covered because each hop opens a new connection.
TLS is unaffected: SNI and certificate checks still use the hostname.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable

import httpcore2
import httpx2

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type AddressPolicy = Callable[[IPAddress], bool]
type Resolver = Callable[[str, int], Awaitable[list[str]]]

# NAT64 well-known prefix: the last 32 bits embed an IPv4 address.
NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


class BlockedAddressError(httpcore2.ConnectError):
    """The host resolves to an address that probes must not reach."""


class DNSResolutionError(httpcore2.ConnectError):
    """The host name could not be resolved."""


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in NAT64_PREFIX:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def is_public_address(address: IPAddress) -> bool:
    """True only for globally routable addresses.

    Rejects private, loopback, link-local (including 169.254.169.254, the
    cloud metadata service), CGNAT, unspecified, reserved, multicast and
    documentation ranges, and IPv4 addresses hidden in IPv6 forms.
    """
    if isinstance(address, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            return is_public_address(embedded)
    return address.is_global and not address.is_multicast


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DNSResolutionError(f"cannot resolve {host}: {exc.strerror}") from exc
    # Keep the resolver order, without duplicates.
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class GuardedBackend(httpcore2.AsyncNetworkBackend):
    def __init__(
        self,
        policy: AddressPolicy = is_public_address,
        resolver: Resolver = system_resolver,
        delegate: httpcore2.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._delegate = delegate or httpcore2.AnyIOBackend()

    async def _validated_addresses(self, host: str, port: int) -> list[str]:
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            addresses = await self._resolver(host, port)
        if not addresses:
            raise DNSResolutionError(f"cannot resolve {host}: no address")
        for address in addresses:
            # Strict: one non-public address blocks the whole host.
            if not self._policy(ipaddress.ip_address(address.split("%", 1)[0])):
                raise BlockedAddressError(f"{host} resolves to non-public address {address}")
        return addresses

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore2 interface)
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        last_error: Exception | None = None
        for address in await self._validated_addresses(host, port):
            try:
                # Connect to the validated address: no second resolution.
                return await self._delegate.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore2.ConnectError as exc:
                last_error = exc
        if last_error is None:
            raise DNSResolutionError(f"cannot resolve {host}: no address")
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore2 interface)
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise BlockedAddressError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class GuardedTransport(httpx2.AsyncHTTPTransport):
    """HTTP transport whose connections all go through GuardedBackend."""

    def __init__(self, backend: GuardedBackend) -> None:
        super().__init__(trust_env=False)
        # httpx2 does not expose network_backend, so replace its connection pool.
        # This relies on the private _pool attribute: the SSRF redirect tests
        # fail if an httpx2 upgrade breaks it.
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(trust_env=False),
            network_backend=backend,
        )
