"""Scrape ACLED listing hubs (e.g. /region/middle-east) for crisis/analysis article links.

Public HTML only (no OAuth read API). Pattern aligned with agents/acled_reference.py.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from services.http_client import CircuitOpenError, HttpClient, get_http_client

logger = logging.getLogger(__name__)

DEFAULT_HUBS = ("https://acleddata.com/region/middle-east",)
PATH_PREFIXES = ("/conflict/", "/update/", "/report/", "/expert-comment/", "/analysis/")
USER_AGENT = "DigitalWarRoom/1.0 (OSINT analysis; crisis listing scrape)"


def _hub_urls() -> List[str]:
    raw = (os.getenv("ACLED_CRISIS_HUB_URLS") or "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return list(DEFAULT_HUBS)


def _max_pages() -> int:
    try:
        return max(1, min(24, int((os.getenv("ACLED_CRISIS_MAX_PAGES") or "12").strip())))
    except (TypeError, ValueError):
        return 12


def _extract_article_links(html: str, base_url: str) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = (m.group(1) or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if "acleddata.com" not in (parsed.netloc or "").lower():
            continue
        path = (parsed.path or "").lower()
        if not any(path.startswith(p) for p in PATH_PREFIXES):
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def _extract_text_from_html(html: str, max_len: int = 2200) -> str:
    if not html or not isinstance(html, str):
        return ""
    s = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    s = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()[:max_len]


def _extract_title(html: str) -> str:
    if not html:
        return ""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    return ""


def _scrape_one_sync(url: str, timeout: float = 18.0) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
        title = _extract_title(html)
        excerpt = _extract_text_from_html(html)
        if not excerpt and not title:
            return {"url": url, "error": "empty_page"}
        return {"url": url, "title": title or url, "excerpt": excerpt, "source": "ACLED Crisis"}
    except Exception as e:
        logger.info("ACLED crisis fetch failed %s: %s", url, e)
        return {"url": url, "error": str(e)}


async def _fetch_hub_and_pages(client: HttpClient, hub: str, budget: int, collected: Set[str]) -> List[Dict[str, Any]]:
    try:
        resp = await client.request(
            "GET",
            hub,
            retries=2,
            timeout=_float_timeout(),
            service_name="acled_crisis_hub",
            headers={"User-Agent": USER_AGENT},
        )
    except Exception as e:
        logger.warning("ACLED crisis hub failed %s: %s", hub, e)
        return []

    links = _extract_article_links(resp.text, hub)[: budget + 20]
    results: List[Dict[str, Any]] = []
    for u in links:
        if u in collected:
            continue
        if len(collected) >= budget:
            break
        try:
            r2 = await client.request(
                "GET",
                u,
                retries=1,
                timeout=_float_timeout(),
                service_name="acled_crisis_article",
                headers={"User-Agent": USER_AGENT},
            )
            html = r2.text
            title = _extract_title(html)
            excerpt = _extract_text_from_html(html)
            collected.add(u)
            if excerpt or title:
                results.append({"url": u, "title": title or u, "excerpt": excerpt, "source": "ACLED Crisis"})
            else:
                results.append({"url": u, "error": "empty_page"})
        except Exception as e:
            results.append({"url": u, "error": str(e)})
    return results


async def fetch_acled_crisis_pages_async(conflict: str) -> List[Dict[str, Any]]:
    """Fetch crisis/analysis pages linked from configured ACLED region hubs."""
    del conflict  # reserved for future conflict-specific hub mapping
    hubs = _hub_urls()
    budget = _max_pages()
    collected: Set[str] = set()
    all_rows: List[Dict[str, Any]] = []
    client = get_http_client()
    for hub in hubs:
        if len(collected) >= budget:
            break
        try:
            rows = await _fetch_hub_and_pages(client, hub, budget - len(collected), collected)
            all_rows.extend(rows)
        except CircuitOpenError:
            logger.warning("ACLED crisis async fetch skipped for %s: circuit breaker open", hub)
            continue

    return all_rows[:budget]


def _float_timeout() -> float:
    try:
        return float((os.getenv("ACLED_CRISIS_HTTP_TIMEOUT") or "22").strip())
    except (TypeError, ValueError):
        return 22.0


def fetch_acled_crisis_pages_sync(conflict: str) -> List[Dict[str, Any]]:
    """Sync wrapper using per-URL fetch (no asyncio from sync callers)."""
    hubs = _hub_urls()
    budget = _max_pages()
    collected: Set[str] = set()
    all_rows: List[Dict[str, Any]] = []
    timeout = _float_timeout()

    for hub in hubs:
        if len(collected) >= budget:
            break
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
                resp = client.get(hub)
                resp.raise_for_status()
                links = _extract_article_links(resp.text, hub)
        except Exception as e:
            logger.warning("ACLED crisis hub failed %s: %s", hub, e)
            continue
        for u in links:
            if u in collected or len(collected) >= budget:
                if len(collected) >= budget:
                    break
                continue
            one = _scrape_one_sync(u, timeout=min(25.0, timeout))
            collected.add(u)
            all_rows.append(one)

    return all_rows[:budget]
