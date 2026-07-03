"""HTTP fetch for Kubikus (local DNS often fails; site uses windows-1251)."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

HOST = "www.kubikus.ru"
IP = "93.188.43.146"
BASE = f"http://{HOST}"

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


def _wait(delay: float = 1.2) -> None:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < delay:
        time.sleep(delay - elapsed)


def kubikus_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return f"{BASE}/{path.lstrip('/')}"


def fetch_text(path: str, *, delay: float = 1.2) -> str:
    global _last_request
    _wait(delay)
    parsed = urlparse(kubikus_url(path))
    target = f"http://{IP}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    with httpx.Client(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
        response = client.get(target, headers=DEFAULT_HEADERS)
        response.raise_for_status()
        _last_request = time.monotonic()
        return response.content.decode("cp1251", errors="ignore")
