"""Playwright fallback for LiveLib (DDoS-Guard)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = ROOT / "data" / "processed" / "livelib_session.json"

_lock = threading.Lock()
_browser_ctx: dict[str, Any] = {}


def _load_session_cookies(context) -> None:
    if not SESSION_PATH.exists():
        return
    try:
        context.add_cookies(json.loads(SESSION_PATH.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        pass


def _save_session_cookies(context) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(context.cookies(), ensure_ascii=False), encoding="utf-8")


def _ensure_browser(headless: bool = True):
    if _browser_ctx.get("page"):
        return _browser_ctx["page"]
    with _lock:
        if _browser_ctx.get("page"):
            return _browser_ctx["page"]
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        _load_session_cookies(context)
        page = context.new_page()
        _browser_ctx.update({"pw": pw, "browser": browser, "context": context, "page": page})
        return page


def close_browser() -> None:
    with _lock:
        context = _browser_ctx.get("context")
        if context:
            try:
                _save_session_cookies(context)
            except Exception:  # noqa: BLE001
                pass
        for key in ("context", "browser", "pw"):
            obj = _browser_ctx.pop(key, None)
            if obj and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:  # noqa: BLE001
                    pass
            if obj and hasattr(obj, "stop"):
                try:
                    obj.stop()
                except Exception:  # noqa: BLE001
                    pass


def fetch_html(url: str, wait_ms: int = 2500, headless: bool = True) -> str:
    page = _ensure_browser(headless=headless)
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    for _ in range(6):
        html = page.content()
        if "DDoS-Guard" not in html and len(html) > 8000:
            return html
        time.sleep(wait_ms / 1000)
    return page.content()


def is_blocked_html(html: str) -> bool:
    return "DDoS-Guard" in html or len(html) < 3000
