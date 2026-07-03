from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from bookfinder.dns_resolve import prepare_request
from bookfinder.fetch_policy import CircuitBreaker, policy_for
from bookfinder.livelib_fetch import is_http_blocked, mark_http_blocked

COOKIE_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "http_cookies"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

JSON_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
}


class RateLimitedClient:
    """HTTP client with per-host delays, retries, cookies and circuit breaker."""

    def __init__(
        self,
        delay_sec: float | None = None,
        timeout: httpx.Timeout | float | None = None,
        warmup: bool = False,
        max_retries: int | None = None,
        use_livelib_browser: bool = True,
        proxy: str | None = None,
        trust_env: bool = True,
    ) -> None:
        self.base_delay = delay_sec
        self.max_retries_override = max_retries
        self.use_livelib_browser = use_livelib_browser
        self._last_request: dict[str, float] = {}
        self._adaptive_delay: dict[str, float] = {}
        self._warmed: set[str] = set()
        self.circuit = CircuitBreaker()
        COOKIE_DIR.mkdir(parents=True, exist_ok=True)

        proxy_url = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

        if isinstance(timeout, (int, float)):
            timeout_cfg = httpx.Timeout(timeout)
        elif timeout is None:
            timeout_cfg = httpx.Timeout(connect=45.0, read=180.0, write=60.0, pool=30.0)
        else:
            timeout_cfg = timeout

        self.client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=timeout_cfg,
            follow_redirects=True,
            http2=False,
            proxy=proxy_url,
            trust_env=trust_env,
        )
        if warmup:
            self._warmup_host("https://fantasy-worlds.net/lib/")

    def _cookie_path(self, host: str) -> Path:
        safe = host.replace(":", "_")
        return COOKIE_DIR / f"{safe}.json"

    def _load_cookies(self, host: str) -> dict[str, str]:
        path = self._cookie_path(host)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_cookies(self, host: str, response: httpx.Response) -> None:
        jar = dict(self._load_cookies(host))
        for key, value in response.cookies.items():
            jar[key] = value
        if jar:
            self._cookie_path(host).write_text(json.dumps(jar, ensure_ascii=False, indent=2), encoding="utf-8")

    def _delay_for(self, url: str) -> float:
        pol = policy_for(url)
        host = urlparse(url).netloc.lower()
        if self.base_delay is not None:
            base = self.base_delay
        else:
            base = self._adaptive_delay.get(host, pol.min_delay)
        jitter = random.uniform(0.85, 1.15)
        return min(pol.max_delay, base * jitter)

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        delay = self._delay_for(url)
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def _warmup_host(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if host in self._warmed:
            return
        pol = policy_for(url)
        if not pol.warmup_url:
            self._warmed.add(host)
            return
        try:
            cookies = self._load_cookies(host)
            headers = self._nav_headers(pol.warmup_url, pol.default_referer)
            response = self.client.get(pol.warmup_url, headers=headers, cookies=cookies)
            self._save_cookies(host, response)
            time.sleep(random.uniform(1.0, 2.5))
        except Exception:  # noqa: BLE001
            pass
        self._warmed.add(host)

    def _nav_headers(self, url: str, referer: str | None) -> dict[str, str]:
        pol = policy_for(url)
        ref = referer or pol.default_referer
        headers: dict[str, str] = {
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if ref else "none",
        }
        if ref:
            headers["Referer"] = ref
        if url.endswith(".json") or "api." in urlparse(url).netloc:
            headers.update(JSON_HEADERS)
            headers["Sec-Fetch-Dest"] = "empty"
            headers["Sec-Fetch-Mode"] = "cors"
        return headers

    def _adjust_delay(self, url: str, success: bool) -> None:
        host = urlparse(url).netloc.lower()
        pol = policy_for(url)
        current = self._adaptive_delay.get(host, pol.min_delay)
        if success:
            self._adaptive_delay[host] = max(pol.min_delay, current * 0.92)
        else:
            self._adaptive_delay[host] = min(pol.max_delay, current * 1.35)

    def _livelib_via_browser(self, url: str) -> httpx.Response:
        from bookfinder.livelib_browser import fetch_html, is_blocked_html

        mark_http_blocked()
        html = fetch_html(url)
        request = httpx.Request("GET", url)
        if is_blocked_html(html):
            self.circuit.record_failure(url)
            self._adjust_delay(url, False)
            raise httpx.HTTPStatusError(
                "LiveLib blocked in browser",
                request=request,
                response=httpx.Response(403, request=request),
            )
        self.circuit.record_success(url)
        self._adjust_delay(url, True)
        return httpx.Response(200, text=html, request=request)

    def get(self, url: str, retries: int | None = None, referer: str | None = None) -> httpx.Response:
        host = urlparse(url).netloc.lower()
        is_livelib = "livelib" in host

        if is_livelib and self.use_livelib_browser and (is_http_blocked() or self.circuit.is_open(url)):
            return self._livelib_via_browser(url)

        if self.circuit.is_open(url):
            pause = self.circuit.pause_remaining(url)
            raise RuntimeError(f"Circuit open for {host_key(url)}, retry in {int(pause)}s")

        pol = policy_for(url)
        attempts = retries if retries is not None else (self.max_retries_override or pol.max_retries)
        if is_livelib:
            attempts = 1
        last_error: Exception | None = None

        self._warmup_host(url)

        for attempt in range(attempts):
            self._wait(url)
            try:
                cookies = self._load_cookies(host)
                headers = self._nav_headers(url, referer)
                req_url, extra_headers, sni = prepare_request(url)
                headers.update(extra_headers)
                if sni:
                    request = httpx.Request(
                        "GET",
                        req_url,
                        headers=headers,
                        extensions={"sni_hostname": sni},
                    )
                    response = self.client.send(request, cookies=cookies)
                else:
                    response = self.client.get(req_url, headers=headers, cookies=cookies)
                self._last_request[host] = time.monotonic()
                self._save_cookies(host, response)

                if response.status_code == 403 and is_livelib:
                    mark_http_blocked()
                    if self.use_livelib_browser:
                        try:
                            return self._livelib_via_browser(url)
                        except httpx.HTTPStatusError as exc:
                            last_error = exc
                    else:
                        last_error = httpx.HTTPStatusError(
                            "403",
                            request=response.request,
                            response=response,
                        )
                    raise RuntimeError(
                        f"LiveLib HTTP blocked for {url}; use scripts/fetch_livelib_playwright.py"
                    ) from last_error

                if response.status_code in {403, 429, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else 10 * (attempt + 1)
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    self.circuit.record_failure(url)
                    self._adjust_delay(url, False)
                    time.sleep(min(120, wait))
                    continue

                response.raise_for_status()
                self.circuit.record_success(url)
                self._adjust_delay(url, True)
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                last_error = exc
                self.circuit.record_failure(url)
                self._adjust_delay(url, False)
                time.sleep(min(90, 4 * (2**attempt) + random.uniform(0, 2)))

        raise RuntimeError(f"GET failed for {url}: {last_error}") from last_error

    def get_text(self, url: str, referer: str | None = None, retries: int | None = None) -> str:
        return self.get(url, referer=referer, retries=retries).text

    def get_json(self, url: str, referer: str | None = None, retries: int | None = None) -> dict:
        return self.get(url, referer=referer, retries=retries).json()

    def close(self) -> None:
        self.client.close()
        if self.use_livelib_browser:
            try:
                from bookfinder.livelib_browser import close_browser

                close_browser()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def host_key(url: str) -> str:
    return urlparse(url).netloc.lower()
