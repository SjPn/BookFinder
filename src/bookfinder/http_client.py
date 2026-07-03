from __future__ import annotations

import time
from typing import Callable

import httpx

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

DEFAULT_TIMEOUT = httpx.Timeout(connect=30.0, read=180.0, write=60.0, pool=30.0)
LIVELIB_HOME = "https://www.livelib.ru/"


class RateLimitedClient:
    def __init__(
        self,
        delay_sec: float = 3.0,
        timeout: httpx.Timeout | float | None = None,
        warmup: bool = True,
        max_retries: int = 6,
    ) -> None:
        self.delay_sec = delay_sec
        self.max_retries = max_retries
        self._last_request = 0.0
        timeout_cfg = DEFAULT_TIMEOUT if timeout is None else timeout
        if isinstance(timeout_cfg, (int, float)):
            timeout_cfg = httpx.Timeout(timeout_cfg)
        self.client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=timeout_cfg,
            follow_redirects=True,
        )
        if warmup:
            self._warmup_livelib()

    def _warmup_livelib(self) -> None:
        try:
            self.client.get(
                LIVELIB_HOME,
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                },
            )
            time.sleep(2)
        except Exception:  # noqa: BLE001
            pass

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay_sec:
            time.sleep(self.delay_sec - elapsed)

    def _livelib_headers(self, referer: str | None = None) -> dict[str, str]:
        return {
            "Referer": referer or LIVELIB_HOME,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Sec-Fetch-User": "?1",
        }

    def get(self, url: str, retries: int | None = None, referer: str | None = None) -> httpx.Response:
        is_livelib = "livelib.ru" in url
        attempts = retries if retries is not None else self.max_retries
        last_error: Exception | None = None

        for attempt in range(attempts):
            self._wait()
            try:
                headers = self._livelib_headers(referer) if is_livelib else None
                if referer and not is_livelib:
                    headers = {"Referer": referer}
                response = self.client.get(url, headers=headers)
                self._last_request = time.monotonic()

                if response.status_code == 403 and is_livelib:
                    self._warmup_livelib()
                    time.sleep(15 * (attempt + 1))
                    last_error = httpx.HTTPStatusError("403 forbidden", request=response.request, response=response)
                    continue
                if response.status_code in {429, 502, 503, 504}:
                    time.sleep(10 * (attempt + 1))
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code} retryable",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                last_error = exc
                if is_livelib:
                    self._warmup_livelib()
                time.sleep(min(60, 5 * (2**attempt)))
        raise RuntimeError(f"GET failed for {url}: {last_error}") from last_error

    def get_text(self, url: str, referer: str | None = None) -> str:
        return self.get(url, referer=referer).text

    def get_json(self, url: str, referer: str | None = None) -> dict:
        return self.get(url, referer=referer).json()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def fetch_with_cache(
    client: RateLimitedClient,
    url: str,
    cache_path,
    parser: Callable[[str], object],
    force: bool = False,
):
    from pathlib import Path

    path = Path(cache_path)
    if path.exists() and not force:
        return parser(path.read_text(encoding="utf-8", errors="ignore"))
    html = client.get_text(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return parser(html)
