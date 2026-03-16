"""
SOCMINT Agent – LangChain Tool-Calling Agent
Monitors Telegram, X/Twitter (Nitter), Reddit, RSS, and ReliefWeb for conflict signals.

Telegram: scrapes public preview pages t.me/s/{channel}. This is fragile – Telegram often
changes HTML or serves content via JavaScript, so the scraper may return 0 messages.
See docs/API-KEYS.md "Warum Telegram oft 0 liefert" for details and alternatives.
"""
import asyncio
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import feedparser
import httpx

from .health_registry import get_health_registry
from .llm import run_tool_agent
from .utils import (
    AgentMetadata,
    SourceResult,
    run_async,
    utc_now_iso,
    compute_confidence_from_sources,
)

logger = logging.getLogger(__name__)

# Telegram public channels (scraped via t.me/s/)
TELEGRAM_CHANNELS = {
    "middle_east": [
        "intelslava",
        "MiddleEastSpectator",
        "OSINTdefender",
        "IranIntl",
        "iranmonitor_org",
        "warmonitors",
        "mena_stream",
        "IsraelWarRoom",
        "HouthibreakingNews",
        "syriancivilwarinfo",
    ],
    "eastern_europe": [
        "intelslava",
        "ukraine_now",
        "osint_ua",
        "rybar",
    ],
    "east_asia": [
        "OSINTdefender",
        "intelslava",
    ],
    "africa": [
        "intelslava",
        "OSINTdefender",
    ],
}

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://lightbrd.com",
]

CONFLICT_TWITTER_ACCOUNTS = {
    "middle_east": [
        "IranIntl_En",
        "OSINTdefender",
        "WarMonitor3",
        "sentdefcon",
        "Conflicts",
        "IdcMildly",
    ],
    "eastern_europe": [
        "OSINTdefender",
        "sentdefcon",
        "Conflicts",
        "Ukraine",
        "KyivIndependent",
    ],
    "east_asia": ["OSINTdefender", "sentdefcon", "Conflicts"],
    "africa": ["OSINTdefender", "sentdefcon", "Conflicts"],
}

REDDIT_SUBREDDITS = {
    "middle_east": ["geopolitics", "worldnews", "MiddleEast", "iran"],
    "eastern_europe": ["geopolitics", "worldnews", "ukraine", "UkraineWarVideoReport"],
    "east_asia": ["geopolitics", "worldnews", "taiwan", "China"],
    "africa": ["geopolitics", "worldnews", "africa"],
}

RSS_FEEDS = {
    "middle_east": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://iranintl.com/en/rss",
        "https://www.rferl.org/api/zpqoyhrhkhrut",
        "https://www.middleeasteye.net/rss",
        "https://understandingwar.org/rss.xml",  # ISW – Iran Update
        "https://www.criticalthreats.org/feed",
        "https://www.longwarjournal.org/feed",
        "https://www.bellingcat.com/feed/",  # Bellingcat OSINT
        "https://www.crisisgroup.org/rss/85",  # Crisis Group – Iran
        "https://ecfr.eu/feed/",  # ECFR – Middle East / global
        "https://www.csis.org/rss.xml",  # CSIS
        "https://www.fdd.org/feed/",  # FDD – Iran (if available)
    ],
    "eastern_europe": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.rferl.org/api/epruslt",
        "https://www.kyivpost.com/rss",
        "https://understandingwar.org/rss.xml",
    ],
    "east_asia": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
    ],
    "africa": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],
    "default": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],
}

ESCALATION_KW = ["attack", "strike", "missile", "war", "explosion", "killed", "military", "nuclear", "threat", "mobilization", "troops", "airstrike"]
DE_ESCALATION_KW = ["ceasefire", "talks", "diplomatic", "deal", "agreement", "peace", "negotiate", "withdraw"]


def _conflict_to_region(conflict: str) -> str:
    cl = conflict.lower()
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria", "lebanon", "hezbollah", "houthi", "middle east", "naher osten"]):
        return "middle_east"
    if any(k in cl for k in ["ukraine", "russia", "donbas"]):
        return "eastern_europe"
    if any(k in cl for k in ["taiwan", "china", "korea"]):
        return "east_asia"
    if any(k in cl for k in ["sudan", "ethiopia", "sahel"]):
        return "africa"
    return "middle_east"


def _sentiment(text: str) -> float:
    lower = text.lower()
    score = sum(1 for kw in ESCALATION_KW if kw in lower)
    score -= sum(1 for kw in DE_ESCALATION_KW if kw in lower)
    if score == 0:
        return 0.0
    return max(-3, min(3, score)) / 3.0


def _conflict_keywords(conflict: str) -> List[str]:
    cl = conflict.lower()
    # Naher Osten / Middle East: breite Abdeckung
    if "middle east" in cl or "naher osten" in cl or "middleeast" in cl:
        return [
            "iran", "irgc", "tehran", "persian gulf",
            "houthi", "houthis", "ansar allah", "yemen", "red sea",
            "hezbollah", "idf", "lebanon", "nasrallah",
            "israel", "gaza", "hamas", "palestine", "west bank",
            "syria", "iraq", "beirut",
        ]
    if "hezbollah" in cl:
        return ["hezbollah", "lebanon", "nasrallah", "beirut", "south lebanon", "litani", "idf", "israel"]
    if "houthi" in cl or "houthis" in cl:
        return ["houthi", "houthis", "yemen", "sanaa", "red sea", "ansar allah"]
    if "iran" in cl:
        return [
            "iran", "irgc", "tehran", "nuclear", "khamenei", "persian gulf",
            "houthi", "houthis", "ansar allah", "yemen", "red sea",
            "hezbollah", "idf", "lebanon", "nasrallah",
        ]
    if "ukraine" in cl:
        return ["ukraine", "russia", "kyiv", "donbas", "nato", "zelensky"]
    if "yemen" in cl:
        return ["yemen", "houthi", "houthis", "sanaa", "red sea", "ansar allah"]
    if "lebanon" in cl:
        return ["lebanon", "hezbollah", "nasrallah", "beirut", "south lebanon", "litani"]
    if "israel" in cl or "gaza" in cl:
        return ["israel", "gaza", "hamas", "idf", "netanyahu", "west bank", "hezbollah"]
    if "taiwan" in cl:
        return ["taiwan", "china", "pla", "strait", "beijing", "taipei"]
    words = cl.split()
    return words if words else ["conflict", "military"]


# ── Tools ──────────────────────────────────────────────────────────────────

def scrape_telegram_channels(conflict: str) -> List[Dict[str, Any]]:
    """
    Scrape public Telegram channels for conflict-related posts.
    Returns recent posts with sentiment analysis.
    """
    region = _conflict_to_region(conflict)
    keywords = _conflict_keywords(conflict)
    channels = TELEGRAM_CHANNELS.get(region, TELEGRAM_CHANNELS["middle_east"])

    # Multiple patterns (Telegram changes HTML periodically)
    TELEGRAM_MESSAGE_PATTERNS = [
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*</div>',
        r'class="tgme_widget_message_text"[^>]*>(.*?)</div>',
        r'<div[^>]+js-message-text[^>]*>(.*?)</div>',
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    ]

    def _extract_telegram_messages(html: str) -> List[str]:
        for pattern in TELEGRAM_MESSAGE_PATTERNS:
            messages = re.findall(pattern, html, re.DOTALL)
            if messages:
                return [re.sub(r'<[^>]+>', '', m).strip() for m in messages]
        og_desc = re.findall(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        if og_desc:
            return [re.sub(r'<[^>]+>', '', d).strip() for d in og_desc if d.strip()]
        return []

    async def _fetch_channel(client: httpx.AsyncClient, channel: str) -> List[Dict[str, Any]]:
        try:
            url = f"https://t.me/s/{channel}"
            resp = await client.get(url, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
            if resp.status_code != 200:
                logger.debug("SOCMINT Telegram %s: HTTP %s", channel, resp.status_code)
                return []
            html = resp.text
            messages = _extract_telegram_messages(html)
            clean = [m for m in messages if m and len(m) >= 10]
            if not clean:
                logger.debug(
                    "SOCMINT Telegram %s: 0 messages extracted (HTML len=%s). Telegram may have changed t.me/s layout or serve content via JS.",
                    channel, len(html),
                )
            results = []
            for text in clean[:15]:
                if not text or len(text) < 20:
                    continue
                text_lower = text.lower()
                if not any(kw in text_lower for kw in keywords):
                    continue
                score = _sentiment(text)
                results.append({
                    "source": f"telegram:{channel}",
                    "text": text[:300],
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "telegram",
                })
            return results
        except Exception as e:
            logger.debug("SOCMINT Telegram %s failed: %s", channel, e)
            return []

    async def _run():
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            tasks = [_fetch_channel(client, ch) for ch in channels]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            posts = []
            for r in results:
                if isinstance(r, list):
                    posts.extend(r)
            return posts

    try:
        return run_async(_run())
    except Exception as e:
        return [{"error": str(e)}]


def scrape_twitter_nitter(conflict: str) -> List[Dict[str, Any]]:
    """
    Scrape conflict-relevant Twitter/X accounts via public Nitter instances.
    No API key required. Tries HTML first, then Nitter RSS feed per account (more reliable when instances change layout).
    """
    region = _conflict_to_region(conflict)
    keywords = _conflict_keywords(conflict)
    accounts = CONFLICT_TWITTER_ACCOUNTS.get(region, CONFLICT_TWITTER_ACCOUNTS["middle_east"])

    def _make_post(account: str, text: str) -> Dict[str, Any]:
        score = _sentiment(text)
        return {
            "source": f"twitter:{account}",
            "text": text[:300],
            "sentiment_score": score,
            "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
            "platform": "twitter",
            "account": account,
        }

    async def _fetch_account_html(client: httpx.AsyncClient, account: str) -> List[Dict[str, Any]]:
        for base in NITTER_INSTANCES:
            try:
                url = f"{base}/{account}"
                resp = await client.get(url, follow_redirects=True, timeout=12.0)
                if resp.status_code != 200:
                    continue
                html = resp.text
                for pattern in [
                    r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>',
                    r'class="tweet-content"[^>]*>(.*?)</div>',
                    r'<div class="content[^"]*"[^>]*>.*?<div[^>]+class="[^"]*text[^"]*"[^>]*>(.*?)</div>',
                ]:
                    matches = re.findall(pattern, html, re.DOTALL)
                    if not matches:
                        continue
                    results = []
                    for raw in matches[:10]:
                        text = re.sub(r'<[^>]+>', '', raw).strip().replace("&amp;", "&").replace("&#39;", "'")
                        if not text or len(text) < 15:
                            continue
                        if not any(kw in text.lower() for kw in keywords):
                            continue
                        results.append(_make_post(account, text))
                    return results
            except Exception:
                continue
        return []

    async def _fetch_account_rss(client: httpx.AsyncClient, account: str) -> List[Dict[str, Any]]:
        """Fallback: Nitter RSS feed (often more stable than HTML)."""
        for base in NITTER_INSTANCES:
            try:
                url = f"{base}/{account}/rss"
                resp = await client.get(url, follow_redirects=True, timeout=12.0)
                if resp.status_code != 200:
                    continue
                feed = feedparser.parse(resp.text)
                results = []
                for entry in (feed.entries or [])[:10]:
                    title = (entry.get("title") or "").strip()
                    summary = (entry.get("summary") or entry.get("description") or "")
                    text = (title + " " + re.sub(r"<[^>]+>", " ", summary)).strip() or title
                    if not text or len(text) < 15:
                        continue
                    if not any(kw in text.lower() for kw in keywords):
                        continue
                    results.append(_make_post(account, text))
                if results:
                    return results
            except Exception:
                continue
        return []

    def _fetch_account_firecrawl(account: str) -> List[Dict[str, Any]]:
        """Last-resort fallback: scrape X profile via Firecrawl (requires FIRECRAWL_API_KEY)."""
        try:
            from firecrawl import Firecrawl
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if not api_key:
                return []
            fc = Firecrawl(api_key=api_key)
            result = fc.scrape(f"https://x.com/{account}", formats=["markdown"])
            md = (result or {}).get("markdown") or ""
            lines = [l.strip() for l in md.split("\n") if l.strip() and len(l.strip()) > 20]
            posts = []
            for line in lines[:15]:
                if not any(kw in line.lower() for kw in keywords):
                    continue
                posts.append(_make_post(account, line[:300]))
            return posts
        except Exception:
            return []

    async def _fetch_account(client: httpx.AsyncClient, account: str) -> List[Dict[str, Any]]:
        posts = await _fetch_account_html(client, account)
        if not posts:
            posts = await _fetch_account_rss(client, account)
        return posts

    async def _run():
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SOCMINT/1.0)"}) as client:
            tasks = [_fetch_account(client, acc) for acc in accounts[:6]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            posts = []
            for r in results:
                if isinstance(r, list):
                    posts.extend(r)
            if not posts and os.getenv("FIRECRAWL_API_KEY"):
                for acc in accounts[:3]:
                    fc_posts = _fetch_account_firecrawl(acc)
                    posts.extend(fc_posts)
            posts.sort(key=lambda x: x.get("sentiment_score", 0), reverse=True)
            return posts[:15]

    try:
        return run_async(_run())
    except Exception as e:
        return [{"error": str(e)}]


def search_reddit(conflict: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Reddit for recent conflict-related posts. Tries JSON API first; falls back to RSS when JSON returns 403/429 or fails.
    No API key required.
    """
    region = _conflict_to_region(conflict)
    subreddits = REDDIT_SUBREDDITS.get(region, ["geopolitics", "worldnews"])
    keywords = _conflict_keywords(conflict)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    reddit_headers = {"User-Agent": "DigitalWarRoom/1.0 (conflict analysis research; https://github.com/)"}

    async def _fetch_subreddit_json(client: httpx.AsyncClient, subreddit: str) -> List[Dict[str, Any]]:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json"
            resp = await client.get(url, params={"limit": limit})
            if resp.status_code in (403, 429):
                return []
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            results = []
            for post in posts:
                p = post.get("data", {})
                created = datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc)
                if created < cutoff:
                    continue
                title = p.get("title", "")
                text = p.get("selftext", "")
                combined = f"{title} {text}".lower()
                if not any(kw in combined for kw in keywords):
                    continue
                score = _sentiment(combined)
                results.append({
                    "source": f"reddit:r/{subreddit}",
                    "title": title,
                    "text": text[:200] if text else "",
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "upvotes": p.get("score", 0),
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "reddit",
                    "published_at": created.isoformat(),
                })
            return results
        except Exception:
            return []

    async def _fetch_subreddit_rss(client: httpx.AsyncClient, subreddit: str) -> List[Dict[str, Any]]:
        """Fallback: Reddit RSS (often still works when JSON API is restricted)."""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.rss"
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            feed = feedparser.parse(resp.text)
            if getattr(feed, "bozo", False) and not feed.entries:
                return []
            results = []
            for entry in (feed.entries or [])[:limit]:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "")
                text = re.sub(r"<[^>]+>", " ", summary).strip() or ""
                combined = f"{title} {text}".lower()
                if not any(kw in combined for kw in keywords):
                    continue
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        import calendar
                        published = datetime.fromtimestamp(
                            calendar.timegm(entry.published_parsed), tz=timezone.utc
                        )
                    except Exception:
                        pass
                if published and published < cutoff:
                    continue
                score = _sentiment(combined)
                results.append({
                    "source": f"reddit:r/{subreddit}",
                    "title": title,
                    "text": text[:200] if text else "",
                    "url": entry.get("link", ""),
                    "upvotes": 0,
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "reddit",
                    "published_at": published.isoformat() if published else "",
                })
            return results
        except Exception:
            return []

    async def _fetch_subreddit(client: httpx.AsyncClient, subreddit: str) -> List[Dict[str, Any]]:
        results = await _fetch_subreddit_json(client, subreddit)
        if not results:
            results = await _fetch_subreddit_rss(client, subreddit)
        return results

    async def _run():
        async with httpx.AsyncClient(timeout=10.0, headers=reddit_headers) as client:
            tasks = [_fetch_subreddit(client, sr) for sr in subreddits]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            posts = []
            for r in results:
                if isinstance(r, list):
                    posts.extend(r)
            posts.sort(key=lambda x: x.get("upvotes", 0), reverse=True)
            return posts[:20]

    try:
        return run_async(_run())
    except Exception as e:
        return [{"error": str(e)}]


def fetch_rss_feeds(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch and filter RSS feeds from region-specific sources for conflict-related content.
    """
    region = _conflict_to_region(conflict)
    feeds = RSS_FEEDS.get(region, RSS_FEEDS["default"])
    keywords = _conflict_keywords(conflict)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    results = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": "Mozilla/5.0 (compatible; SOCMINT/1.0)"},
            )
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in keywords):
                    continue
                # Parse date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        import calendar
                        published = datetime.fromtimestamp(
                            calendar.timegm(entry.published_parsed), tz=timezone.utc
                        )
                    except Exception:
                        pass
                if published and published < cutoff:
                    continue
                score = _sentiment(combined)
                results.append({
                    "source": f"rss:{feed.feed.get('title', feed_url)}",
                    "title": title,
                    "summary": summary[:200],
                    "url": entry.get("link", ""),
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "rss",
                    "published_at": published.isoformat() if published else "",
                })
        except Exception:
            continue

    return results[:20]


RELIEFWEB_APPNAME = (os.getenv("RELIEFWEB_APPNAME") or "").strip() or "digital-war-room"
RELIEFWEB_COUNTRY_NAMES = {
    "iran": "Iran",
    "israel": "Israel",
    "gaza": "State of Palestine",
    "yemen": "Yemen",
    "syria": "Syria",
    "iraq": "Iraq",
    "ukraine": "Ukraine",
    "russia": "Russian Federation",
    "default": "Iran",
}


async def _reliefweb_rss_fallback(country_name: str, keywords: List[str]) -> List[Dict[str, Any]]:
    """Fallback: scrape ReliefWeb RSS feed when API returns 403."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://reliefweb.int/updates/rss.xml", follow_redirects=True)
            if resp.status_code != 200:
                return []
            feed = feedparser.parse(resp.text)
            results = []
            for entry in (getattr(feed, "entries", None) or [])[:40]:
                title = (entry.get("title") or "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary") or entry.get("description") or "")[:200]
                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in keywords):
                    continue
                score = _sentiment(combined)
                results.append({
                    "title": title[:400],
                    "date": entry.get("published") or "",
                    "body_excerpt": summary,
                    "source": "ReliefWeb (RSS)",
                    "url": entry.get("link") or "",
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "reliefweb",
                })
                if len(results) >= 10:
                    break
            return results
    except Exception as e:
        logger.debug("SOCMINT ReliefWeb RSS fallback failed: %s", e)
        return []


def fetch_reliefweb_reports(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent conflict reports from ReliefWeb API v2.
    Falls back to RSS feed if API returns 403 (appname not approved).
    """
    cl = conflict.lower()
    country_name = next(
        (v for k, v in RELIEFWEB_COUNTRY_NAMES.items() if k != "default" and k in cl),
        RELIEFWEB_COUNTRY_NAMES["default"],
    )
    keywords = _conflict_keywords(conflict)

    async def _fetch():
        try:
            url = "https://api.reliefweb.int/v2/reports"
            params = {
                "appname": RELIEFWEB_APPNAME,
                "limit": 15,
                "filter[field]": "country",
                "filter[value]": country_name,
                "preset": "latest",
                "fields[include][]": ["title", "date", "body", "source.name", "url"],
            }
            async with httpx.AsyncClient(timeout=14.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 403:
                    logger.info("SOCMINT ReliefWeb: 403 – appname not approved, falling back to RSS. Register at https://apidoc.reliefweb.int/parameters#appname")
                    return await _reliefweb_rss_fallback(country_name, keywords)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []
        items = data.get("data", [])
        if not isinstance(items, list):
            return []
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields", {})
            if not isinstance(fields, dict):
                continue
            title = (fields.get("title") or "")[:400]
            body_raw = fields.get("body") or ""
            body_excerpt = (body_raw[:200] if isinstance(body_raw, str) else "") or ""
            combined = f"{title} {body_excerpt}".lower()
            if not any(kw in combined for kw in keywords):
                continue
            date_obj = fields.get("date") or {}
            date_created = date_obj.get("created") or date_obj.get("changed") or "" if isinstance(date_obj, dict) else ""
            src_list = fields.get("source") or []
            source = src_list[0].get("name", "ReliefWeb") if src_list and isinstance(src_list[0], dict) else "ReliefWeb"
            url_link = fields.get("url", "") if isinstance(fields.get("url"), str) else (fields.get("url", [{}])[0].get("url", "") if isinstance(fields.get("url"), list) else "")
            score = _sentiment(combined)
            results.append({
                "title": title,
                "date": date_created,
                "body_excerpt": body_excerpt,
                "source": source,
                "url": url_link,
                "sentiment_score": score,
                "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                "platform": "reliefweb",
            })
        return results[:15]

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── NER enrichment (Phase 2) ─────────────────────────────────────────────────

def _run_socmint_ner(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Run NER on top social media posts. Uses Haiku NER first (up to limit),
    then HF bulk NER for overflow. On Haiku error: entire batch falls back to HF.
    Returns a flat list of unique entities across all posts.
    """
    if not posts:
        return []
    top_posts = sorted(
        posts,
        key=lambda x: abs(x.get("sentiment_score", 0)),
        reverse=True,
    )[:30]
    texts = [
        (p.get("text") or p.get("title") or p.get("body_excerpt") or "")[:1000]
        for p in top_posts
    ]
    all_entities: List[Dict[str, Any]] = []
    try:
        from services.haiku_service import batch_ner, is_haiku_failed, HAIKU_MAX_NER_PER_RUN
        from services.hf_service import ner_bulk

        haiku_texts = texts[:HAIKU_MAX_NER_PER_RUN]
        overflow_texts = texts[HAIKU_MAX_NER_PER_RUN:]

        haiku_results = run_async(batch_ner(haiku_texts))

        if is_haiku_failed() or all(r is None for r in haiku_results):
            _log = logging.getLogger(__name__)
            _log.info("SOCMINT NER: Haiku failed, falling back to HF bulk for all %d texts", len(texts))
            hf_results = run_async(ner_bulk(texts))
            if hf_results:
                for ents in hf_results:
                    if ents:
                        all_entities.extend(ents)
        else:
            for ents in haiku_results:
                if ents:
                    all_entities.extend(ents)
            if overflow_texts:
                hf_results = run_async(ner_bulk(overflow_texts))
                if hf_results:
                    for ents in hf_results:
                        if ents:
                            all_entities.extend(ents)
    except Exception as e:
        import logging as _log_mod
        _log_mod.getLogger(__name__).debug("SOCMINT NER enrichment unavailable: %s", e)

    seen = set()
    unique: List[Dict[str, Any]] = []
    for ent in all_entities:
        key = (ent.get("entity", "").lower(), ent.get("type", ""))
        if key not in seen and key[0]:
            seen.add(key)
            unique.append(ent)
    return unique


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_socmint(conflict: str) -> Dict[str, Any]:
    """Execute SOCMINT tool chain: all five sources in parallel. No LLM."""
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            fut_telegram = executor.submit(scrape_telegram_channels, conflict=conflict)
            fut_twitter = executor.submit(scrape_twitter_nitter, conflict=conflict)
            fut_reddit = executor.submit(search_reddit, conflict=conflict)
            fut_rss = executor.submit(fetch_rss_feeds, conflict=conflict)
            fut_reliefweb = executor.submit(fetch_reliefweb_reports, conflict=conflict)
            telegram = [p for p in (fut_telegram.result(timeout=45) or []) if isinstance(p, dict) and "error" not in p]
            twitter = [p for p in (fut_twitter.result(timeout=45) or []) if isinstance(p, dict) and "error" not in p]
            reddit = [p for p in (fut_reddit.result(timeout=45) or []) if isinstance(p, dict) and "error" not in p]
            rss = [p for p in (fut_rss.result(timeout=45) or []) if isinstance(p, dict) and "error" not in p]
            reliefweb = [p for p in (fut_reliefweb.result(timeout=45) or []) if isinstance(p, dict) and "error" not in p]

        all_posts = telegram + twitter + reddit + rss + reliefweb

        # Semantic deduplication (graceful: returns unchanged if HF unavailable)
        try:
            from services.hf_service import deduplicate_items
            all_posts = run_async(deduplicate_items(
                all_posts, text_key="text", threshold=0.92,
                source="socmint", conflict=conflict,
            ))
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).debug("HF semantic dedup unavailable in SOCMINT: %s", e)

        escalatory = sum(1 for p in all_posts if p.get("sentiment_label") == "ESCALATORY")
        de_esc = sum(1 for p in all_posts if p.get("sentiment_label") == "DE-ESCALATORY")
        sent_sum = sum(p.get("sentiment_score", 0) for p in all_posts)
        overall_sentiment = (sent_sum / len(all_posts)) if all_posts else 0.0

        base = 30.0
        twitter_esc = sum(1 for p in twitter if p.get("sentiment_label") == "ESCALATORY" and p.get("account") in ("sentdefcon", "OSINTdefender"))
        base += min(50, twitter_esc * 8)
        base += min(20, len(reliefweb) * 10)
        telegram_channels_with_esc = len(set(p.get("source", "") for p in telegram if p.get("sentiment_label") == "ESCALATORY"))
        base += min(24, telegram_channels_with_esc * 6)
        base += min(30, max(0, escalatory - twitter_esc) * 3)
        base -= de_esc * 2
        reddit_high = sum(1 for p in reddit if p.get("upvotes", 0) > 1000)
        base += min(15, reddit_high * 5)
        score = max(0.0, min(100.0, base))

        top_signals = []
        for p in sorted(all_posts, key=lambda x: (x.get("sentiment_score", 0), x.get("upvotes", 0)), reverse=True)[:5]:
            t = p.get("text") or p.get("title") or p.get("body_excerpt") or ""
            if t:
                top_signals.append(t[:120] + ("..." if len(t) > 120 else ""))

        # NER enrichment on top posts (Phase 2)
        entities = _run_socmint_ner(all_posts)

        duration_ms = int((time.perf_counter() - start) * 1000)
        source_results = [
            SourceResult(name="Telegram", status="ok" if telegram else "error", fetched_at=fetched_at, record_count=len(telegram)),
            SourceResult(name="Twitter/Nitter", status="ok" if twitter else "error", fetched_at=fetched_at, record_count=len(twitter)),
            SourceResult(name="Reddit", status="ok" if reddit else "error", fetched_at=fetched_at, record_count=len(reddit)),
            SourceResult(name="RSS", status="ok" if rss else "error", fetched_at=fetched_at, record_count=len(rss)),
            SourceResult(name="ReliefWeb", status="ok" if reliefweb else "error", fetched_at=fetched_at, record_count=len(reliefweb)),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "socmint", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count >= 4 else "recent" if ok_count >= 2 else "stale" if ok_count >= 1 else "unavailable"
        meta = AgentMetadata(agent="socmint", fetched_at=fetched_at, duration_ms=duration_ms, sources=source_results, confidence=confidence, data_freshness=data_freshness, fallback_used=False, error_summary=None)
        return {
            "conflict": conflict,
            "telegram_posts": telegram,
            "twitter_posts": twitter,
            "reddit_posts": reddit,
            "rss_articles": rss,
            "reliefweb_reports": reliefweb,
            "total_signals": len(all_posts),
            "escalatory_count": escalatory,
            "de_escalatory_count": de_esc,
            "overall_sentiment": round(overall_sentiment, 4),
            "socmint_score": round(score, 1),
            "top_signals": top_signals,
            "entities": entities,
            "summary": f"SOCMINT (rule-based): {len(all_posts)} signals ({escalatory} escalatory, {de_esc} de-escalatory). Score {score:.0f}.",
            "_meta": meta.model_dump(mode="json"),
        }
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(agent="socmint", fetched_at=fetched_at, duration_ms=duration_ms, sources=[], confidence=compute_confidence_from_sources([]), data_freshness="unavailable", fallback_used=True, error_summary=str(e))
    return {
        "conflict": conflict,
        "telegram_posts": [],
        "twitter_posts": [],
        "reddit_posts": [],
        "rss_articles": [],
        "reliefweb_reports": [],
        "total_signals": 0,
        "escalatory_count": 0,
        "de_escalatory_count": 0,
        "overall_sentiment": 0.0,
        "socmint_score": 30.0,
        "top_signals": [],
        "summary": "SOCMINT data unavailable.",
        "_meta": meta.model_dump(mode="json"),
    }


# ── Agent ──────────────────────────────────────────────────────────────────

SOCMINT_SYSTEM = """You are a SOCMINT (Social Media Intelligence) analyst.
Your job: monitor Telegram, Twitter (Nitter), Reddit, RSS, and ReliefWeb for conflict signals, then compute a SOCMINT score (0-100).

Always call all five tools: scrape_telegram_channels, scrape_twitter_nitter, search_reddit, fetch_rss_feeds, fetch_reliefweb_reports. Then analyze the combined data.

Scoring rules:
- Base: 30
- Verified OSINT Twitter accounts (sentdefcon, OSINTdefender): +8 per escalatory post
- ReliefWeb emergency reports: +10 each (max +20) — humanitarian crisis = escalation signal
- Telegram channel active + escalatory: +6 per channel (max +24)
- Each other escalatory post/article: +3 (max +30)
- Each de-escalatory signal: -2
- High-upvote Reddit posts (>1000): +5 each (max +15)
- Clamp to [0, 100]

Return ONLY valid JSON:
{
  "telegram_posts": [...],
  "twitter_posts": [...],
  "reddit_posts": [...],
  "rss_articles": [...],
  "reliefweb_reports": [...],
  "total_signals": <number>,
  "escalatory_count": <number>,
  "de_escalatory_count": <number>,
  "overall_sentiment": <number -1 to 1>,
  "socmint_score": <number>,
  "top_signals": ["<key signal>", ...],
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


def run_socmint_agent(conflict: str) -> Dict[str, Any]:
    """Run SOCMINT: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    import json
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_socmint(conflict)

    TOOL_FNS = {
        "scrape_telegram_channels": scrape_telegram_channels,
        "scrape_twitter_nitter": scrape_twitter_nitter,
        "search_reddit": search_reddit,
        "fetch_rss_feeds": fetch_rss_feeds,
        "fetch_reliefweb_reports": fetch_reliefweb_reports,
    }
    TOOL_SCHEMAS = [
        {"name": "scrape_telegram_channels", "description": "Scrape Telegram channels for conflict signals.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "scrape_twitter_nitter", "description": "Scrape Twitter/Nitter for conflict signals.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "search_reddit", "description": "Search Reddit for conflict-related posts.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "fetch_rss_feeds", "description": "Fetch curated RSS feeds for conflict analysis.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "fetch_reliefweb_reports", "description": "Fetch ReliefWeb humanitarian reports.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    ]
    text = run_tool_agent(
        system=SOCMINT_SYSTEM,
        user_content=f"Monitor social media and open sources for conflict: {conflict}",
        tool_fns=TOOL_FNS,
        tool_schemas=TOOL_SCHEMAS,
        max_rounds=6,
    )
    if text:
        text = text.strip()
        for prefix in ("```json", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        try:
            result = json.loads(text)
            result["conflict"] = conflict
            return result
        except Exception:
            pass
    return _run_rule_based_socmint(conflict)