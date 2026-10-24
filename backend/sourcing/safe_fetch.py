"""Fetching URLs that come from users or scraped listings, without letting them reach internal services.

Every hop (including each redirect, followed manually) must be http(s) and resolve only to public addresses;
responses are streamed and abandoned past a size cap. Known gap: the hostname is resolved here and again by the
HTTP client, so a DNS-rebinding host could in principle answer differently between the two lookups.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import httpx

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/126.0 Safari/537.36')
MAX_REDIRECTS = 3
TIMEOUT = 10


class UnsafeURL(ValueError):
    pass


def client():
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False,
        headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml,image/*;q=0.9,*/*;q=0.8',
                 'Accept-Language': 'en-US,en;q=0.9'})


async def resolve(host):
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def blocked(address):
    ip = ipaddress.ip_address(address.split('%')[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global)


async def check(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise UnsafeURL(f'not a public http(s) URL: {url[:100]}')
    host = parts.hostname
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await resolve(host)
        except OSError as exc:
            raise UnsafeURL(f'cannot resolve {host}') from exc
    if not addresses or any(blocked(a) for a in addresses):
        raise UnsafeURL(f'{host} resolves to a non-public address')


async def fetch(http, url, max_bytes):
    """GET url through http (a client from client()). Returns (body, final_url, content_type), or None when the
    URL is unsafe, fails, redirects too often or exceeds max_bytes."""
    for _ in range(MAX_REDIRECTS + 1):
        try:
            await check(url)
            async with http.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                response.raise_for_status()
                body = b''
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        return None
                return body, url, response.headers.get('content-type', '')
        except (UnsafeURL, httpx.HTTPError):
            return None
    return None
