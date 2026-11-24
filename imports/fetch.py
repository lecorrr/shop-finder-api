"""Downloading a feed from a URL a shop owner typed in.

A server that fetches user-supplied URLs can be pointed at its own network (SSRF), so only
https to public addresses is allowed, redirects are not followed and size is capped.
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "shop-finder-api feed importer"


class FetchError(Exception):
    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class Download:
    content: bytes
    content_type: str


Resolver = Callable[[str, int], list[str]]


def resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def check_url(url: str, resolver: Resolver = resolve) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchError("only https:// feed URLs are accepted", transient=False)
    if not parts.hostname or parts.username or parts.password:
        raise FetchError("the URL needs a host and no user name or password", transient=False)
    try:
        addresses = resolver(parts.hostname, parts.port or 443)
    except OSError as error:
        raise FetchError(f"cannot resolve {parts.hostname}", transient=True) from error
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise FetchError(f"{parts.hostname} is not a public address", transient=False)


def fetch_feed(
    url: str, *, client: httpx.Client | None = None, resolver: Resolver = resolve
) -> Download:
    check_url(url, resolver)
    http = client or httpx.Client(
        timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": USER_AGENT}
    )
    try:
        with http, http.stream("GET", url) as response:
            _check_status(response)
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_BYTES:
                raise FetchError("the feed is larger than 5 MB", transient=False)
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise FetchError("the feed is larger than 5 MB", transient=False)
                chunks.append(chunk)
            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            return Download(b"".join(chunks), content_type)
    except httpx.TransportError as error:
        raise FetchError(f"download failed: {type(error).__name__}", transient=True) from error


def _check_status(response: httpx.Response) -> None:
    status = response.status_code
    if response.is_redirect:
        raise FetchError(f"the URL redirects ({status}); give the final address", transient=False)
    if status == 429 or status >= 500:
        raise FetchError(f"the server answered {status}", transient=True)
    if status >= 400:
        raise FetchError(f"the server answered {status}", transient=False)
