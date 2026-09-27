# 0007. SSRF protection for outgoing probes

- Status: Accepted
- Date: 2026-09-27

## Context

The worker sends HTTP requests to URLs that users submit through the API. Without a guard, anyone who can add a site can make the worker reach internal systems (Server-Side Request Forgery): the local network, services bound to loopback, and on AWS the instance metadata service at `169.254.169.254`, which hands out IAM credentials.

Validating the URL when it is created is not enough:

- **DNS rebinding**: a name can resolve to a public address when it is checked, then to an internal one when the worker connects.
- **Redirects**: a public site can answer with a redirect to an internal address.
- **Alternative forms**: IPv4 addresses hidden in IPv6 (`::ffff:169.254.169.254`, the NAT64 prefix `64:ff9b::/96`), and names such as `localhost`.

## Decision

- **Validate at connection time, in the network backend.** The probe client (`httpx2`) opens its sockets through a custom `httpcore2` network backend (`GuardedBackend`, in `pulsewatch.worker.ssrf`). For every new TCP connection it:
  1. resolves the host itself (IP literals are checked directly);
  2. rejects the connection if **any** resolved address is not public;
  3. connects to a validated address, without resolving the name again.

  Redirects are followed (at most 5), and each hop opens a new connection, which goes through the same check. TLS is unaffected: SNI and certificate verification still use the hostname.
- **Address policy**: an address is allowed only if it is globally routable (`ipaddress.is_global`) and not multicast. IPv4 addresses embedded in IPv6 (IPv4-mapped, NAT64) are extracted and checked as IPv4. This rejects private, loopback, link-local (including `169.254.169.254`), CGNAT, unspecified, reserved and documentation ranges, in IPv4 and IPv6.
- **No bypass**:
  - Proxy environment variables are ignored (`trust_env=False`), so no proxy can route requests around the check.
  - Unix sockets are refused.
  - The API only accepts http and https URLs, without credentials.
- **Blocked probes are recorded**, not dropped: `ok = false`, no status code, and an error starting with `blocked_address`, so users see why their site is not monitored.
- **No production setting relaxes the policy.** Tests inject a policy that allows their local fake server. The deployed worker always uses the strict one.
- The worker uses `httpx2`, the successor of `httpx` already chosen for the API tests (#7), rather than `httpx` as written in ADR 0005.

## Alternatives considered

- **Validate URLs only when they are created, in the API**: defeated by DNS rebinding and by redirects.
- **Resolve, then rewrite the URL with the IP address**: needs manual handling of the `Host` header and of TLS SNI and certificate verification, and every redirect has to be rewritten again. The network backend gets the same guarantee without touching the request.
- **Disable redirects**: simpler, but many sites redirect (http to https, trailing slash), which would record false failures. Redirects are safe with the connection-level check.
- **Egress proxy (for example smokescreen)**: strong isolation, but one more component to run. It is a candidate for later, as defense in depth.

## Consequences

- Internal or private sites cannot be monitored. That is intended for a public-facing monitor.
- `httpx2` does not expose `network_backend`, so `GuardedTransport` replaces its private `_pool` attribute. The version is pinned in `uv.lock`, and the SSRF redirect and end-to-end tests fail if an upgrade breaks this.
- Defense in depth to add with the AWS deployment: IMDSv2 with a hop limit of 1 on the nodes, and Kubernetes NetworkPolicies restricting the worker's egress.
