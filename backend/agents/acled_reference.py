"""
ACLED Reference Analyses – Fetches curated ACLED analysis/report pages and extracts text
for use as context in the supervisor (Iran / Middle East). Content is passed into the
synthesis so agents "pay attention" to these points instead of only linking to them.
"""
import asyncio
import re
from typing import Any, Dict, List

import httpx

# Curated ACLED analysis URLs (updates, expert comments, reports) – used when conflict is Iran/Middle East
ACLED_REFERENCE_URLS = [
    "https://acleddata.com/update/middle-east-special-issue-march-2026",
    "https://acleddata.com/expert-comment/acled-spokesperson-kurdish-dynamics-irans-western-war-zone",
    "https://acleddata.com/report/israel-prepares-ground-invasion-lebanon-hezbollah-formally-joins-war",
]

# Max chars of extracted text per page (to fit in context)
MAX_EXCERPT_PER_PAGE = 2200


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


async def _fetch_one(url: str) -> Dict[str, Any]:
    """Fetch one URL and return { url, title, excerpt } or { url, error }."""
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
    """
    cl = (conflict or "").lower()
    if not any(x in cl for x in ("iran", "us-iran", "middle east", "israel", "gaza", "lebanon", "hezbollah", "yemen", "iraq", "syria")):
        return []
    results: List[Dict[str, Any]] = []
    for url in ACLED_REFERENCE_URLS:
        one = await _fetch_one(url)
        if one.get("excerpt") or one.get("title"):
            results.append(one)
        elif one.get("error"):
            results.append({"url": url, "title": url, "excerpt": f"(Fetch error: {one['error']})"})
    return results


def fetch_acled_reference_analyses_sync(conflict: str) -> List[Dict[str, Any]]:
    """Sync wrapper for use from supervisor (runs in executor)."""
    return asyncio.run(fetch_acled_reference_analyses_async(conflict))
