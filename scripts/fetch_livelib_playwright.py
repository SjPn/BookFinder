"""Fetch LiveLib search pages via Playwright (DDoS-Guard bypass)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.models import BookRecord
from bookfinder.parsers import livelib

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "livelib_search"
SESSION_PATH = OUT / "livelib_session.json"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def pending_books(books: list[BookRecord]) -> list[BookRecord]:
    pending: list[BookRecord] = []
    for book in books:
        if list(SEARCH_DIR.glob(f"{book.external_id}_*.html")):
            continue
        pending.append(book)
    return pending


def fetch_via_search_form(page, query: str, wait_ms: int = 3000) -> str:
    page.goto("https://www.livelib.ru/", wait_until="domcontentloaded", timeout=120_000)
    for _ in range(5):
        if "DDoS-Guard" not in page.content():
            break
        page.wait_for_timeout(wait_ms)

    field = page.locator("#find-text-ll2019, input[name='filter[search]']").first
    field.fill(query, timeout=30_000)
    page.locator("#header-top-search-form").evaluate("form => form.submit()")
    page.wait_for_load_state("domcontentloaded", timeout=120_000)
    for _ in range(5):
        html = page.content()
        if "DDoS-Guard" not in html and len(html) > 10_000:
            return html
        page.wait_for_timeout(wait_ms)
    return page.content()


def fetch_html(page, url: str, wait_ms: int = 3000) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    for _ in range(5):
        html = page.content()
        if "DDoS-Guard" not in html and len(html) > 10_000:
            return html
        page.wait_for_timeout(wait_ms)
    return page.content()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=4.0)
    parser.add_argument("--headless", action="store_true", default=True)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("playwright not installed") from exc

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    books = load_fantlab()
    pending = pending_books(books)
    if args.limit:
        pending = pending[: args.limit]

    print(f"pending {len(pending)} / {len(books)}")
    ok = blocked = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        context = browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        if SESSION_PATH.exists():
            try:
                context.add_cookies(json.loads(SESSION_PATH.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

        fetch_html(page, "https://www.livelib.ru/", wait_ms=5000)
        OUT.mkdir(parents=True, exist_ok=True)
        SESSION_PATH.write_text(json.dumps(context.cookies(), ensure_ascii=False), encoding="utf-8")

        for idx, book in enumerate(pending, start=1):
            safe = "".join(ch if ch.isalnum() else "_" for ch in book.title)[:60]
            path = SEARCH_DIR / f"{book.external_id}_{safe}.html"

            saved = False
            urls = [
                livelib.search_url(book.title),
                livelib.search_url(book.title, book.authors[0] if book.authors else None),
            ]
            for url in urls:
                try:
                    html = fetch_html(page, url)
                    if "DDoS-Guard" in html or len(html) < 5000:
                        continue
                    path.write_text(html, encoding="utf-8")
                    ok += 1
                    saved = True
                    print(f"[{idx}] ok: {book.title}")
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"[{idx}] retry: {book.title} -> {exc}")

            if not saved:
                blocked += 1
                print(f"[{idx}] blocked: {book.title}")
            elif idx % 10 == 0:
                SESSION_PATH.write_text(json.dumps(context.cookies(), ensure_ascii=False), encoding="utf-8")

            time.sleep(args.delay)

        browser.close()

    print(f"saved {ok}, blocked {blocked}")


if __name__ == "__main__":
    main()
