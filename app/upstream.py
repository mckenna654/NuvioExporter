"""Bounded JSON reads with TLS verification and DNS-pinned destination checks."""
from __future__ import annotations

import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

from app import USER_AGENT


class UpstreamError(Exception):
    """Messages are deliberately safe to return without leaking configured URLs."""


PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7'))


def permitted_ip(address, allow_private=False):
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_global and not ip.is_multicast:
        return True
    return allow_private and any(ip in network for network in PRIVATE_NETWORKS if ip.version == network.version)


class JsonFetcher:
    def __init__(self, *, allow_private=False, max_bytes=8 * 1024 * 1024, timeout=15):
        self.allow_private = allow_private
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.slots = threading.BoundedSemaphore(4)
        self.context = ssl.create_default_context()
        # Some macOS Python distributions ship without a configured CA path.
        # Use the system trust bundle, never disable certificate verification.
        if not self.context.get_ca_certs() and Path('/etc/ssl/cert.pem').is_file():
            self.context.load_verify_locations('/etc/ssl/cert.pem')

    def __call__(self, url):
        if not self.slots.acquire(timeout=5):
            raise UpstreamError('The compatibility addon is busy. Retry shortly.')
        try:
            return self._fetch(url)
        except UpstreamError:
            raise
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            raise UpstreamError('The original addon could not be read. Check its connection and configuration.') from None
        finally:
            self.slots.release()

    def _fetch(self, url):
        original = urlsplit(url)
        deadline = time.monotonic() + self.timeout
        for _ in range(4):
            parts = urlsplit(url)
            if (parts.scheme not in {'http', 'https'} or not parts.hostname or
                    parts.username or parts.password or parts.fragment or
                    any(ord(c) < 33 for c in url)):
                raise UpstreamError('The original addon URL is not valid.')
            if (parts.hostname != original.hostname or parts.port != original.port or
                    parts.scheme != original.scheme):
                raise UpstreamError('The original addon redirected to another origin. Update its configured manifest URL.')
            port = parts.port or (443 if parts.scheme == 'https' else 80)
            addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
            if not addresses or any(not permitted_ip(a[4][0], self.allow_private) for a in addresses):
                raise UpstreamError('Private or reserved upstream addresses are blocked. For a trusted LAN addon, enable NUVIOEXPORTER_ALLOW_PRIVATE_UPSTREAM.')
            conn = http.client.HTTPConnection(parts.hostname, port, timeout=self.timeout)
            # Connect to the checked numeric address, without a second DNS lookup.
            # HTTPConnection keeps the original hostname for its Host header.
            last_error = None
            for family, socktype, protocol, _, address in addresses:
                sock = socket.socket(family, socktype, protocol)
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    sock.settimeout(remaining)
                    sock.connect(address)
                    if parts.scheme == 'https':
                        sock = self.context.wrap_socket(sock, server_hostname=parts.hostname)
                    conn.sock = sock
                    break
                except OSError as exc:
                    last_error = exc
                    sock.close()
            if conn.sock is None:
                raise last_error or OSError('Connection unavailable')
            try:
                target = parts.path or '/'
                if parts.query:
                    target += '?' + parts.query
                conn.request('GET', target, headers={'Accept': 'application/json',
                             'Accept-Encoding': 'identity', 'User-Agent': USER_AGENT})
                response = conn.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader('Location')
                    if not location:
                        raise UpstreamError('The original addon returned an invalid redirect.')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise UpstreamError(f'The original addon returned HTTP {response.status}. Retry or check that addon.')
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    raise UpstreamError('The original addon ignored the uncompressed JSON request.')
                length = response.getheader('Content-Length')
                if length and int(length) > self.max_bytes:
                    raise UpstreamError('The original addon response exceeds the safety limit.')
                body = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise UpstreamError('The original addon timed out. Retry shortly.')
                    if conn.sock:
                        conn.sock.settimeout(remaining)
                    chunk = response.read1(min(65536, self.max_bytes + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > self.max_bytes:
                        raise UpstreamError('The original addon response exceeds the safety limit.')
                data = json.loads(body)
                if not isinstance(data, dict) or data.get('error'):
                    raise UpstreamError('The original addon returned an error instead of catalog data.')
                return data
            finally:
                conn.close()
        raise UpstreamError('The original addon redirected too many times.')
