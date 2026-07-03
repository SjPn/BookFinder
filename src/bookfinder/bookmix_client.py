"""HTTPS fetch for BookMix via IP bypass when DNS is broken."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

HOST = "bookmix.ru"
IP = "213.189.208.102"

DEFAULT_HEADERS = {
    "Host": HOST,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

_last_request = 0.0


def _wait(delay: float = 2.0) -> None:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < delay:
        time.sleep(delay - elapsed)


def fetch_text(url: str, *, delay: float = 2.0, timeout: float = 45.0) -> str:
    global _last_request
    _wait(delay)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    target = f"https://{IP}{path}"
    request = httpx.Request(
        "GET",
        target,
        headers=DEFAULT_HEADERS,
        extensions={"sni_hostname": HOST},
    )
    with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        response = client.send(request)
        response.raise_for_status()
        _last_request = time.monotonic()
        return response.text
