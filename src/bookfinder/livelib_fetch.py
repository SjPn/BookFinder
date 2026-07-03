"""LiveLib fetch: skip httpx after DDoS-Guard 403, use Playwright session."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bookfinder.livelib_browser import close_browser, is_blocked_html
from bookfinder.parsers.livelib import search_url

ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = ROOT / "data" / "processed" / "livelib_session.json"
STATE_PATH = ROOT / "data" / "processed" / "livelib_fetch_state.json"


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_http_blocked() -> bool:
    return bool(_load_state().get("http_blocked"))


def mark_http_blocked() -> None:
    state = _load_state()
    if state.get("http_blocked"):
        return
    state["http_blocked"] = True
    state["blocked_at"] = time.time()
    _save_state(state)


def clear_http_blocked() -> None:
    _save_state({"http_blocked": False, "blocked_at": None})


class LiveLibSession:
    """Reusable Playwright session for batch LiveLib search/page fetches."""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def __enter__(self) -> LiveLibSession:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def open(self) -> None:
        if self._page:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        if SESSION_PATH.exists():
            try:
                self._context.add_cookies(json.loads(SESSION_PATH.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        self._page = self._context.new_page()
        self._fetch_page("https://www.livelib.ru/", wait_ms=5000)
        self._save_cookies()

    def close(self) -> None:
        if self._context:
            try:
                self._save_cookies()
            except Exception:  # noqa: BLE001
                pass
        for attr in ("_page", "_context", "_browser"):
            obj = getattr(self, attr, None)
            if obj and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:  # noqa: BLE001
                    pass
            setattr(self, attr, None)
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
        close_browser()

    def _save_cookies(self) -> None:
        if not self._context:
            return
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_PATH.write_text(
            json.dumps(self._context.cookies(), ensure_ascii=False),
            encoding="utf-8",
        )

    def _fetch_page(self, url: str, wait_ms: int = 3000) -> str:
        if not self._page:
            raise RuntimeError("LiveLibSession not open")
        self._page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        for _ in range(6):
            html = self._page.content()
            if not is_blocked_html(html):
                return html
            self._page.wait_for_timeout(wait_ms)
        return self._page.content()

    def _fetch_via_form(self, query: str, wait_ms: int = 3000) -> str:
        if not self._page:
            raise RuntimeError("LiveLibSession not open")
        self._page.goto("https://www.livelib.ru/", wait_until="domcontentloaded", timeout=120_000)
        for _ in range(5):
            if "DDoS-Guard" not in self._page.content():
                break
            self._page.wait_for_timeout(wait_ms)

        field = self._page.locator("#find-text-ll2019, input[name='filter[search]']").first
        field.fill(query, timeout=30_000)
        self._page.locator("#header-top-search-form").evaluate("form => form.submit()")
        self._page.wait_for_load_state("domcontentloaded", timeout=120_000)
        for _ in range(6):
            html = self._page.content()
            if not is_blocked_html(html):
                return html
            self._page.wait_for_timeout(wait_ms)
        return self._page.content()

    def fetch_url(self, url: str) -> str | None:
        mark_http_blocked()
        html = self._fetch_page(url)
        if is_blocked_html(html):
            return None
        return html

    def fetch_search(self, title: str, author: str | None = None) -> str | None:
        """Try direct URLs, then search form. Returns HTML or None."""
        mark_http_blocked()
        queries = []
        if author:
            queries.append(search_url(title, author))
        queries.append(search_url(title))

        for url in queries:
            html = self._fetch_page(url)
            if not is_blocked_html(html):
                return html

        query = f"{author} {title}".strip() if author else title
        html = self._fetch_via_form(query)
        if is_blocked_html(html):
            return None
        return html
