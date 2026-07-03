"""Cache-first stable fetching with content validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx

from bookfinder.dns_resolve import prepare_request
from bookfinder.http_client import RateLimitedClient
from bookfinder.livelib_browser import is_blocked_html
from bookfinder.parsers.fantlab import parse_work_meta, work_url

ROOT = Path(__file__).resolve().parents[2]


def _is_valid_html(html: str, url: str) -> bool:
    if not html or len(html) < 1500:
        return False
    if is_blocked_html(html):
        return False
    if "fantasy-worlds.net" in url and "/lib/id" in url:
        return "poll_mark1_" in html or "download_book_" in html
    if "fantlab.ru/work" in url:
        return "work_name" in html or "fantlab" in html.lower()
    if "livelib.ru" in url:
        return "livelib" in html.lower() and "DDoS-Guard" not in html
    return True


def _is_valid_json(data: object, url: str) -> bool:
    if "responses.json" in url or "workreviews" in url:
        return isinstance(data, (dict, list))
    if not isinstance(data, dict):
        return False
    if "api.fantlab.ru" in url:
        return bool(data.get("work_name") or data.get("work_id") or data.get("rating"))
    return True


def fetch_text(
    client: RateLimitedClient,
    url: str,
    cache_path: Path | str,
    *,
    referer: str | None = None,
    force: bool = False,
    min_bytes: int = 1500,
    retries: int | None = None,
) -> str:
    path = Path(cache_path)
    if path.exists() and not force:
        html = path.read_text(encoding="utf-8", errors="ignore")
        if len(html) >= min_bytes and _is_valid_html(html, url):
            return html

    html = client.get_text(url, referer=referer, retries=retries)
    if len(html) < min_bytes or not _is_valid_html(html, url):
        raise RuntimeError(f"Invalid HTML from {url} ({len(html)} bytes)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return html


def fetch_json(
    client: RateLimitedClient,
    url: str,
    cache_path: Path | str,
    *,
    referer: str | None = None,
    force: bool = False,
    retries: int | None = None,
) -> dict:
    path = Path(cache_path)
    if path.exists() and not force:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if _is_valid_json(data, url):
                return data
        except json.JSONDecodeError:
            pass

    data = client.get_json(url, referer=referer, retries=retries)
    if not _is_valid_json(data, url):
        raise RuntimeError(f"Invalid JSON from {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def fetch_with_cache(
    client: RateLimitedClient,
    url: str,
    cache_path: Path | str,
    parser: Callable[[str], object],
    force: bool = False,
):
    html = fetch_text(client, url, cache_path, force=force)
    return parser(html)


def fetch_fantlab_work(
    client: RateLimitedClient,
    work_id: str,
    api_cache: Path | str,
    html_cache: Path | str,
    *,
    force: bool = False,
    html_only: bool = False,
) -> dict:
    """API first (fast fail), HTML fallback for rating/title/genres."""
    api_url = f"https://api.fantlab.ru/work{work_id}.json"
    html_url = work_url(work_id)
    api_path = Path(api_cache)
    html_path = Path(html_cache)

    if api_path.exists() and not force:
        try:
            data = json.loads(api_path.read_text(encoding="utf-8"))
            if _is_valid_json(data, api_url):
                data.setdefault("source", "api")
                return data
        except json.JSONDecodeError:
            pass

    if not html_only:
        try:
            data = fetch_json(
                client,
                api_url,
                api_path,
                referer="https://fantlab.ru/",
                force=force,
                retries=2,
            )
            data["source"] = "api"
            return data
        except Exception:
            pass

    html = fetch_text(
        client,
        html_url,
        html_path,
        referer="https://fantlab.ru/",
        force=force,
        retries=4,
    )
    data = parse_work_meta(html, work_id)
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def probe_url(client: RateLimitedClient, url: str, timeout_sec: float = 8.0) -> bool:
    try:
        req_url, extra_headers, sni = prepare_request(url)
        headers = dict(client.client.headers)
        headers.update(extra_headers)
        with httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(timeout_sec),
            follow_redirects=True,
            trust_env=True,
        ) as probe:
            if sni:
                request = httpx.Request(
                    "GET",
                    req_url,
                    headers=headers,
                    extensions={"sni_hostname": sni},
                )
                response = probe.send(request)
            else:
                response = probe.get(req_url)
            response.raise_for_status()
            return True
    except Exception:
        return False
