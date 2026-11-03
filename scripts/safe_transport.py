"""DNS-pinned HTTP transport for untrusted, public image URLs.

The adapter resolves and validates every address, then connects to one of those
validated numeric IPs. urllib3 retains the original hostname for TLS SNI,
certificate validation and the HTTP Host header. This closes the DNS
check/connect race without disabling TLS verification.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from common import SkillError, validate_remote_url_syntax


def resolve_public_address(url: str) -> tuple[str, str, str, int]:
    clean = validate_remote_url_syntax(url)
    parsed = urlsplit(clean)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SkillError(f"DNS resolution failed for {host}") from exc
    if not addresses:
        raise SkillError(f"DNS resolution returned no addresses for {host}")
    ips = [address[4][0].split("%", 1)[0] for address in addresses]
    if any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise SkillError("local, private, reserved, or link-local destinations are blocked")
    # Prefer IPv4 when both families are available to avoid IPv6-only failures
    # on networks where AAAA records exist but outbound IPv6 is not routed.
    chosen = next((ip for ip in ips if ipaddress.ip_address(ip).version == 4), ips[0])
    return clean, host, chosen, port


def pinned_adapter_class():
    from requests.adapters import HTTPAdapter
    from urllib3 import connection
    from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
    from urllib3.util import connection as socket_connection

    class PinnedHTTPAdapter(HTTPAdapter):
        def get_connection(self, url, proxies=None):
            # Deliberately refuse proxied downloads: a proxy resolves DNS at
            # its own end and would bypass the local public-address check.
            if proxies and any(proxies.values()):
                raise SkillError("proxies are not supported for pinned image downloads")
            clean, hostname, ip, port = resolve_public_address(url)

            class PinnedHTTPConnection(connection.HTTPConnection):
                def _new_conn(self):
                    return socket_connection.create_connection(
                        (ip, self.port), self.timeout,
                        source_address=self.source_address,
                        socket_options=self.socket_options,
                    )

            class PinnedHTTPSConnection(connection.HTTPSConnection):
                def _new_conn(self):
                    return socket_connection.create_connection(
                        (ip, self.port), self.timeout,
                        source_address=self.source_address,
                        socket_options=self.socket_options,
                    )

            if urlsplit(clean).scheme == "https":
                class PinnedPool(HTTPSConnectionPool):
                    ConnectionCls = PinnedHTTPSConnection
            else:
                class PinnedPool(HTTPConnectionPool):
                    ConnectionCls = PinnedHTTPConnection

            # Pool host remains the original hostname. TLS cert verification
            # and SNI therefore use the domain, NOT the numeric IP.
            return PinnedPool(host=hostname, port=port, maxsize=1, block=True)

        # requests >= 2.32 calls this rather than get_connection().
        def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
            return self.get_connection(request.url, proxies)

    return PinnedHTTPAdapter


def mount_pinned_transport(session):
    """Mount only when using a real requests Session, not a test fake."""
    from urllib3.util.retry import Retry

    retry = Retry(
        total=2, connect=1, read=0, status=2, backoff_factor=0.6,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter_cls = pinned_adapter_class()
    session.mount("https://", adapter_cls(max_retries=retry))
    session.mount("http://", adapter_cls(max_retries=retry))
    return session
