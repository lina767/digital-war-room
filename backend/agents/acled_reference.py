"""
ACLED Reference Analyses – Fetches curated ACLED analysis/report pages and extracts text
for use as context in the supervisor (Iran / Middle East). Content is passed into the
synthesis so agents "pay attention" to these points instead of only linking to them.

When FIRECRAWL_API_KEY is set, uses Firecrawl for robust scraping (markdown, JS support).
Otherwise falls back to httpx + regex. Free Plan: max 2 concurrent Firecrawl requests.
"""

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import httpx

from .health_registry import get_health_registry
from .utils import SourceResult, run_async, utc_now_iso

# Curated ACLED analysis URLs (updates, expert comments, reports) – used when conflict is Iran/Middle East
ACLED_REFERENCE_URLS = [
    "https://acleddata.com/update/middle-east-special-issue-march-2026",
    "https://acleddata.com/expert-comment/acled-spokesperson-kurdish-dynamics-irans-western-war-zone",
    "https://acleddata.com/report/israel-prepares-ground-invasion-lebanon-hezbollah-formally-joins-war",
]

# Max chars of extracted text per page (to fit in context)
MAX_EXCERPT_PER_PAGE = 2200

# Firecrawl Free Plan: max 2 concurrent requests
FIRECRAWL_MAX_CONCURRENT = 2


def _extract_text_from_html(html: str) -> str:
    """Remove script/style, strip tags, collapse whitespace. No external deps."""
    if not html or not isinstance(html, str):
        return ""
    s = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    s = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()[:MAX_EXCERPT_PER_PAGE]


def _extract_title(html: str) -> str:
    """Get <title>...</title> or first <h1>."""
    if not html:
        return ""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    return ""


def _scrape_one_firecrawl(url: str) -> Dict[str, Any]:
    """
    Scrape one URL via Firecrawl SDK (sync). Returns { url, title, excerpt } or { url, error }.
    Used from run_in_executor; respects Free Plan by limiting concurrency in the caller.
    """
    try:
        from firecrawl import Firecrawl

        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            return {"url": url, "error": "FIRECRAWL_API_KEY not set"}
        app = Firecrawl(api_key=api_key)
        result = app.scrape(url, formats=["markdown"])
        if not result:
            return {"url": url, "error": "Scrape failed"}
        # v2 SDK may return dict with success/data or document-like with markdown
        if isinstance(result, dict) and not result.get("success", True):
            return {"url": url, "error": result.get("error", "Scrape failed")}
        data = (result or {}).get("data", result) if isinstance(result, dict) else result
        if not isinstance(data, dict):
            data = {"markdown": str(data)} if data else {}
        markdown = (data.get("markdown") or (result.get("markdown") if isinstance(result, dict) else "") or "").strip()
        meta = data.get("metadata") or (result.get("metadata") if isinstance(result, dict) else {}) or {}
        title = (meta.get("title") or meta.get("ogTitle") or url or "")[:200]
        excerpt = (markdown or "")[:MAX_EXCERPT_PER_PAGE]
        if not excerpt and not title:
            return {"url": url, "error": "No content extracted"}
        return {"url": url, "title": title or url, "excerpt": excerpt}
    except Exception as e:
        return {"url": url, "error": str(e)}


async def _fetch_one(url: str) -> Dict[str, Any]:
    """Fetch one URL via httpx and return { url, title, excerpt } or { url, error }."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "DigitalWarRoom/1.0 (OSINT analysis)"})
            resp.raise_for_status()
            html = resp.text
        title = _extract_title(html)
        excerpt = _extract_text_from_html(html)
        if not excerpt and not title:
            return {"url": url, "error": "No content extracted"}
        return {"url": url, "title": title or url, "excerpt": excerpt[:MAX_EXCERPT_PER_PAGE]}
    except Exception as e:
        return {"url": url, "error": str(e)}


async def fetch_acled_reference_analyses_async(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch curated ACLED analysis pages and return list of { url, title, excerpt }.
    Only runs for Iran / Middle East related conflicts to keep context relevant.
    Uses Firecrawl when FIRECRAWL_API_KEY is set (max 2 concurrent); otherwise httpx fallback.
    """
    cl = (conflict or "").lower()
    if not any(
        x in cl
        for x in ("iran", "us-iran", "middle east", "israel", "gaza", "lebanon", "hezbollah", "yemen", "iraq", "syria")
    ):
        return []
    use_firecrawl = bool(os.getenv("FIRECRAWL_API_KEY"))
    results: List[Dict[str, Any]] = []

    if use_firecrawl:
        sem = asyncio.Semaphore(FIRECRAWL_MAX_CONCURRENT)
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=FIRECRAWL_MAX_CONCURRENT) as executor:

            async def scrape_one(url: str) -> Dict[str, Any]:
                async with sem:
                    return await loop.run_in_executor(executor, _scrape_one_firecrawl, url)

            raw = await asyncio.gather(*(scrape_one(u) for u in ACLED_REFERENCE_URLS), return_exceptions=True)
        for i, one in enumerate(raw):
            if isinstance(one, Exception):
                url = ACLED_REFERENCE_URLS[i] if i < len(ACLED_REFERENCE_URLS) else ""
                results.append({"url": url, "title": url, "excerpt": f"(Fetch error: {one})"})
            elif one.get("excerpt") or one.get("title"):
                results.append(one)
            elif one.get("error"):
                results.append(
                    {
                        "url": one.get("url", ""),
                        "title": one.get("url", ""),
                        "excerpt": f"(Fetch error: {one['error']})",
                    }
                )
    else:
        for url in ACLED_REFERENCE_URLS:
            one = await _fetch_one(url)
            if one.get("excerpt") or one.get("title"):
                results.append(one)
            elif one.get("error"):
                results.append({"url": url, "title": url, "excerpt": f"(Fetch error: {one['error']})"})

    ok_count = len(
        [
            r
            for r in results
            if isinstance(r, dict)
            and (r.get("excerpt") or r.get("title"))
            and not str(r.get("excerpt") or "").startswith("(Fetch error:")
        ]
    )
    source_result = SourceResult(
        name="ACLED Reference",
        status="ok" if ok_count > 0 else "error",
        fetched_at=utc_now_iso(),
        record_count=ok_count,
    )
    reg = get_health_registry()
    if reg:
        reg.record_result(source_result.name, "geoint", source_result)
    return results


def fetch_acled_reference_analyses_sync(conflict: str) -> List[Dict[str, Any]]:
    """Sync wrapper for use from supervisor (runs in executor)."""
    return run_async(fetch_acled_reference_analyses_async(conflict))
