"""
SOCMINT Agent.
Monitors Telegram, X/Twitter (Nitter), Reddit, RSS, and ReliefWeb for conflict signals.

Telegram: scrapes public preview pages t.me/s/{channel}. This is fragile – Telegram often
changes HTML or serves content via JavaScript, so the scraper may return 0 messages.
See docs/API-KEYS.md "Warum Telegram oft 0 liefert" for details and alternatives.
"""

import asyncio
import html as html_module
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from ..config import RELIEFWEB_APPNAME
from ..utils import run_async

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

ESCALATION_KW = [
    "attack",
    "strike",
    "missile",
    "war",
    "explosion",
    "killed",
    "military",
    "nuclear",
    "threat",
    "mobilization",
    "troops",
    "airstrike",
]
DE_ESCALATION_KW = ["ceasefire", "talks", "diplomatic", "deal", "agreement", "peace", "negotiate", "withdraw"]


def _conflict_to_region(conflict: str) -> str:
    cl = conflict.lower()
    if any(
        k in cl
        for k in [
            "iran",
            "israel",
            "gaza",
            "yemen",
            "syria",
            "lebanon",
            "hezbollah",
            "houthi",
            "middle east",
            "naher osten",
        ]
    ):
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


def _extract_og_image_from_html(fragment: str) -> Optional[str]:
    """First og:image or twitter:image from an HTML fragment (post page head)."""
    if not fragment:
        return None
    chunk = fragment[:120000]
    for prop in ("og:image", "og:image:url", "twitter:image"):
        m = re.search(
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            chunk,
            re.I,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
                chunk,
                re.I,
            )
        if m:
            u = html_module.unescape(m.group(1).strip())
            if u.startswith("http") or u.startswith("//"):
                return u if u.startswith("http") else "https:" + u[2:]
    return None


def _reddit_image_from_json_post(p: Dict[str, Any]) -> Optional[str]:
    """Preview / direct image URL from Reddit .json post data."""
    prev = p.get("preview") if isinstance(p.get("preview"), dict) else None
    if prev:
        images = prev.get("images") or []
        if images and isinstance(images[0], dict):
            src = (images[0].get("source") or {}) if isinstance(images[0].get("source"), dict) else {}
            u = src.get("url")
            if isinstance(u, str) and u.startswith("http"):
                return html_module.unescape(u)
    url = (p.get("url") or "").strip()
    if url.startswith("http") and any(
        x in url.lower() for x in ("i.redd.it", "i.redditmedia.com", "preview.redd.it", "gfycat.com")
    ):
        return url
    lower = url.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return url
    thumb = (p.get("thumbnail") or "").strip()
    if thumb.startswith("http") and thumb != "self" and "redditstatic.com" not in thumb:
        return thumb
    return None


def _conflict_keywords(conflict: str) -> List[str]:
    cl = conflict.lower()
    # Naher Osten / Middle East: breite Abdeckung
    if "middle east" in cl or "naher osten" in cl or "middleeast" in cl:
        return [
            "iran",
            "irgc",
            "tehran",
            "persian gulf",
            "houthi",
            "houthis",
            "ansar allah",
            "yemen",
            "red sea",
            "hezbollah",
            "idf",
            "lebanon",
            "nasrallah",
            "israel",
            "gaza",
            "hamas",
            "palestine",
            "west bank",
            "syria",
            "iraq",
            "beirut",
        ]
    if "hezbollah" in cl:
        return ["hezbollah", "lebanon", "nasrallah", "beirut", "south lebanon", "litani", "idf", "israel"]
    if "houthi" in cl or "houthis" in cl:
        return ["houthi", "houthis", "yemen", "sanaa", "red sea", "ansar allah"]
    if "iran" in cl:
        return [
            "iran",
            "irgc",
            "tehran",
            "nuclear",
            "khamenei",
            "persian gulf",
            "houthi",
            "houthis",
            "ansar allah",
            "yemen",
            "red sea",
            "hezbollah",
            "idf",
            "lebanon",
            "nasrallah",
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

_TELEGRAM_MESSAGE_TEXT_PATTERNS = [
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*</div>',
    r'class="tgme_widget_message_text"[^>]*>(.*?)</div>',
    r"<div[^>]+js-message-text[^>]*>(.*?)</div>",
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
]


def _split_telegram_message_blocks(page_html: str) -> List[tuple]:
    """Split t.me/s/ channel HTML into (data_post, inner_html) per message."""
    blocks = re.findall(
        r'<div[^>]+class="[^"]*tgme_widget_message[^"]*"[^>]+data-post="([^"]+)"[^>]*>(.*?)(?=<div[^>]+class="[^"]*tgme_widget_message[^"]*"[^>]+data-post="|\Z)',
        page_html,
        re.DOTALL | re.IGNORECASE,
    )
    return blocks


def _text_from_telegram_block(block_html: str) -> str:
    for pattern in _TELEGRAM_MESSAGE_TEXT_PATTERNS:
        messages = re.findall(pattern, block_html, re.DOTALL)
        if messages:
            return re.sub(r"<[^>]+>", "", messages[0]).strip()
    return ""


def _extract_telegram_media_urls(block_html: str) -> List[str]:
    """Image and video thumbnail URLs from a single message widget (t.me/s HTML)."""
    urls: List[str] = []
    for m in re.finditer(r"background-image\s*:\s*url\(\s*['\"]?([^'\"\)]+)", block_html, re.I):
        u = html_module.unescape(m.group(1).strip())
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http"):
            urls.append(u)
    for m in re.finditer(
        r'<img[^>]+class="[^"]*tgme_widget_message_(?:video_thumb|photo|sticker)_thumb[^"]*"[^>]*\bsrc=["\']([^"\']+)',
        block_html,
        re.I | re.DOTALL,
    ):
        u = html_module.unescape(m.group(1).strip())
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http"):
            urls.append(u)
    for m in re.finditer(
        r'<img[^>]*\bsrc=["\']([^"\']+)["\'][^>]*class="[^"]*tgme_widget_message_(?:video_thumb|photo)',
        block_html,
        re.I | re.DOTALL,
    ):
        u = html_module.unescape(m.group(1).strip())
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http"):
            urls.append(u)
    for m in re.finditer(
        r'<a[^>]+class="[^"]*tgme_widget_message_photo_thumb[^"]*"[^>]+style="[^"]*background-image\s*:\s*url\(\s*[\"\\]?([^\"\\)]+)',
        block_html,
        re.I | re.DOTALL,
    ):
        u = html_module.unescape(m.group(1).strip())
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http"):
            urls.append(u)

    seen: set = set()
    ordered: List[str] = []
    for u in urls:
        if u not in seen and not u.endswith(".svg"):
            seen.add(u)
            ordered.append(u)
    return ordered


def scrape_telegram_channels(conflict: str) -> List[Dict[str, Any]]:
    """
    Scrape public Telegram channels for conflict-related posts.
    Returns recent posts with sentiment analysis plus media_urls (photos, video thumbs).
    """
    region = _conflict_to_region(conflict)
    keywords = _conflict_keywords(conflict)
    channels = TELEGRAM_CHANNELS.get(region, TELEGRAM_CHANNELS["middle_east"])

    def _extract_telegram_messages_flat(html: str) -> List[str]:
        for pattern in _TELEGRAM_MESSAGE_TEXT_PATTERNS:
            messages = re.findall(pattern, html, re.DOTALL)
            if messages:
                return [re.sub(r"<[^>]+>", "", m).strip() for m in messages]
        og_desc = re.findall(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        if og_desc:
            return [re.sub(r"<[^>]+>", "", d).strip() for d in og_desc if d.strip()]
        return []

    async def _fetch_channel(client: httpx.AsyncClient, channel: str) -> List[Dict[str, Any]]:
        try:
            url = f"https://t.me/s/{channel}"
            resp = await client.get(
                url,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
            if resp.status_code != 200:
                logger.debug("SOCMINT Telegram %s: HTTP %s", channel, resp.status_code)
                return []
            page_html = resp.text
            blocks = _split_telegram_message_blocks(page_html)
            results: List[Dict[str, Any]] = []

            if blocks:
                for _post_id, block_inner in blocks[:18]:
                    text = _text_from_telegram_block(block_inner)
                    media_urls = _extract_telegram_media_urls(block_inner)
                    block_plain = re.sub(r"<[^>]+>", " ", block_inner)
                    block_plain_l = block_plain.lower()
                    text_l = text.lower()
                    if not any(kw in text_l for kw in keywords) and not any(kw in block_plain_l for kw in keywords):
                        continue
                    primary = (text or block_plain).strip()
                    if len(primary) < 8 and not media_urls:
                        continue
                    use_text = (text or primary)[:300]
                    score = _sentiment(use_text or block_plain)
                    row: Dict[str, Any] = {
                        "source": f"telegram:{channel}",
                        "text": use_text,
                        "url": f"https://t.me/{_post_id}" if _post_id else f"https://t.me/s/{channel}",
                        "sentiment_score": score,
                        "sentiment_label": "ESCALATORY"
                        if score > 0.2
                        else "DE-ESCALATORY"
                        if score < -0.2
                        else "NEUTRAL",
                        "platform": "telegram",
                    }
                    if media_urls:
                        row["media_urls"] = media_urls
                        row["thumbnail_url"] = media_urls[0]
                    results.append(row)
                return results

            messages = _extract_telegram_messages_flat(page_html)
            clean = [m for m in messages if m and len(m) >= 10]
            if not clean:
                logger.debug(
                    "SOCMINT Telegram %s: 0 messages extracted (HTML len=%s). Telegram may have changed t.me/s layout or serve content via JS.",
                    channel,
                    len(page_html),
                )
            for text in clean[:15]:
                if not text or len(text) < 20:
                    continue
                text_lower = text.lower()
                if not any(kw in text_lower for kw in keywords):
                    continue
                score = _sentiment(text)
                results.append(
                    {
                        "source": f"telegram:{channel}",
                        "text": text[:300],
                        "url": f"https://t.me/s/{channel}",
                        "sentiment_score": score,
                        "sentiment_label": "ESCALATORY"
                        if score > 0.2
                        else "DE-ESCALATORY"
                        if score < -0.2
                        else "NEUTRAL",
                        "platform": "telegram",
                    }
                )
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

    def _make_post(
        account: str,
        text: str,
        media_urls: Optional[List[str]] = None,
        *,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        score = _sentiment(text)
        row: Dict[str, Any] = {
            "source": f"twitter:{account}",
            "text": text[:300],
            "url": url or f"https://x.com/{account}",
            "sentiment_score": score,
            "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
            "platform": "twitter",
            "account": account,
        }
        if media_urls:
            row["media_urls"] = media_urls
            row["thumbnail_url"] = media_urls[0]
        return row

    async def _fetch_account_html(client: httpx.AsyncClient, account: str) -> List[Dict[str, Any]]:
        for base in NITTER_INSTANCES:
            try:
                url = f"{base}/{account}"
                resp = await client.get(url, follow_redirects=True, timeout=12.0)
                if resp.status_code != 200:
                    continue
                html = resp.text
                # Collect status permalinks for best-effort provenance.
                status_urls: List[str] = []
                for m in re.finditer(rf'href="(?P<href>/{re.escape(account)}/status/\d+[^"]*)"', html, re.I):
                    href = (m.group("href") or "").strip()
                    if not href:
                        continue
                    full = f"{base}{href}"
                    if full not in status_urls:
                        status_urls.append(full)
                for pattern in [
                    r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>',
                    r'class="tweet-content"[^>]*>(.*?)</div>',
                    r'<div class="content[^"]*"[^>]*>.*?<div[^>]+class="[^"]*text[^"]*"[^>]*>(.*?)</div>',
                ]:
                    matches = re.findall(pattern, html, re.DOTALL)
                    if not matches:
                        continue
                    results = []
                    for i, raw in enumerate(matches[:10]):
                        text = re.sub(r"<[^>]+>", "", raw).strip().replace("&amp;", "&").replace("&#39;", "'")
                        if not text or len(text) < 15:
                            continue
                        if not any(kw in text.lower() for kw in keywords):
                            continue
                        permalink = status_urls[i] if i < len(status_urls) else f"{base}/{account}"
                        results.append(_make_post(account, text, url=permalink))
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
                    summary = entry.get("summary") or entry.get("description") or ""
                    text = (title + " " + re.sub(r"<[^>]+>", " ", summary)).strip() or title
                    if not text or len(text) < 15:
                        continue
                    if not any(kw in text.lower() for kw in keywords):
                        continue
                    permalink = (entry.get("link") or "").strip() if isinstance(entry, dict) else ""
                    if not permalink and hasattr(entry, "link"):
                        permalink = str(getattr(entry, "link", "") or "").strip()
                    if not permalink:
                        permalink = f"{base}/{account}"
                    media_urls: List[str] = []
                    for link in entry.get("links") or []:
                        if not isinstance(link, dict):
                            continue
                        href = (link.get("href") or "").strip()
                        typ = (link.get("type") or "").lower()
                        if not href.startswith("http"):
                            continue
                        if typ.startswith("image/") or "twimg.com" in href or "pbs.twimg.com" in href:
                            media_urls.append(href)
                    mcontent = entry.get("media_content") if hasattr(entry, "get") else getattr(entry, "media_content", None)
                    if mcontent:
                        for mc in mcontent:
                            if isinstance(mc, dict):
                                u = mc.get("url") or mc.get("href")
                                if isinstance(u, str) and u.startswith("http"):
                                    media_urls.append(u)
                    if media_urls:
                        seen_m: set = set()
                        media_urls = [u for u in media_urls if not (u in seen_m or seen_m.add(u))]
                    results.append(_make_post(account, text, media_urls=media_urls or None, url=permalink))
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
            lines = [line.strip() for line in md.split("\n") if line.strip() and len(line.strip()) > 20]
            posts = []
            for line in lines[:15]:
                if not any(kw in line.lower() for kw in keywords):
                    continue
                posts.append(_make_post(account, line[:300], url=f"https://x.com/{account}"))
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
                og_image = _reddit_image_from_json_post(p)
                row = {
                    "source": f"reddit:r/{subreddit}",
                    "title": title,
                    "text": text[:200] if text else "",
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "upvotes": p.get("score", 0),
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY"
                    if score > 0.2
                    else "DE-ESCALATORY"
                    if score < -0.2
                    else "NEUTRAL",
                    "platform": "reddit",
                    "published_at": created.isoformat(),
                }
                if og_image:
                    row["og_image"] = og_image
                    row["media_urls"] = [og_image]
                    row["thumbnail_url"] = og_image
                results.append(row)
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
                summary = entry.get("summary") or entry.get("description") or ""
                text = re.sub(r"<[^>]+>", " ", summary).strip() or ""
                combined = f"{title} {text}".lower()
                if not any(kw in combined for kw in keywords):
                    continue
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        import calendar

                        published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
                    except (TypeError, ValueError, OverflowError):
                        published = None
                if published and published < cutoff:
                    continue
                score = _sentiment(combined)
                post_url = entry.get("link", "")
                og_image: Optional[str] = None
                mt = entry.get("media_thumbnail") if hasattr(entry, "get") else getattr(entry, "media_thumbnail", None)
                if mt:
                    if isinstance(mt, list) and mt:
                        first = mt[0]
                        u = None
                        if isinstance(first, dict):
                            u = first.get("url")
                        elif hasattr(first, "get"):
                            u = first.get("url")
                        if isinstance(u, str) and u.startswith("http"):
                            og_image = u
                    elif isinstance(mt, dict) and mt.get("url"):
                        og_image = mt["url"]
                if not og_image and summary:
                    im = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary, re.I)
                    if im:
                        cand = html_module.unescape(im.group(1).strip())
                        if cand.startswith("//"):
                            cand = "https:" + cand[2:]
                        if cand.startswith("http") and "redditstatic.com" not in cand:
                            og_image = cand
                row = {
                    "source": f"reddit:r/{subreddit}",
                    "title": title,
                    "text": text[:200] if text else "",
                    "url": post_url,
                    "upvotes": 0,
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY"
                    if score > 0.2
                    else "DE-ESCALATORY"
                    if score < -0.2
                    else "NEUTRAL",
                    "platform": "reddit",
                    "published_at": published.isoformat() if published else "",
                }
                if og_image:
                    row["og_image"] = og_image
                    row["media_urls"] = [og_image]
                    row["thumbnail_url"] = og_image
                results.append(row)
            return results
        except Exception:
            return []

    async def _fill_reddit_og_images(client: httpx.AsyncClient, posts: List[Dict[str, Any]]) -> None:
        sem = asyncio.Semaphore(3)

        async def _one(row: Dict[str, Any]) -> None:
            if row.get("og_image") or not row.get("url"):
                return
            u = row["url"]
            if not isinstance(u, str) or not u.startswith("http"):
                return
            async with sem:
                try:
                    r = await client.get(
                        u,
                        follow_redirects=True,
                        timeout=6.0,
                        headers={"User-Agent": reddit_headers["User-Agent"]},
                    )
                    if r.status_code != 200:
                        return
                    img = _extract_og_image_from_html(r.text)
                    if img:
                        row["og_image"] = img
                        row["media_urls"] = [img]
                        row["thumbnail_url"] = img
                except Exception:
                    return

        need = [p for p in posts if isinstance(p, dict) and p.get("platform") == "reddit" and not p.get("og_image") and p.get("url")]
        if not need:
            return
        await asyncio.gather(*[_one(p) for p in need[:8]])

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
            await _fill_reddit_og_images(client, posts)
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

                        published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
                    except (TypeError, ValueError, OverflowError):
                        published = None
                if published and published < cutoff:
                    continue
                score = _sentiment(combined)
                results.append(
                    {
                        "source": f"rss:{feed.feed.get('title', feed_url)}",
                        "title": title,
                        "summary": summary[:200],
                        "url": entry.get("link", ""),
                        "sentiment_score": score,
                        "sentiment_label": "ESCALATORY"
                        if score > 0.2
                        else "DE-ESCALATORY"
                        if score < -0.2
                        else "NEUTRAL",
                        "platform": "rss",
                        "published_at": published.isoformat() if published else "",
                    }
                )
        except Exception:
            continue

    return results[:20]


RELIEFWEB_COUNTRY_NAMES = {
    "iran": "Iran",
    "israel": "Israel",
    "gaza": "State of Palestine",
    "yemen": "Yemen",
    "lebanon": "Lebanon",
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
                results.append(
                    {
                        "title": title[:400],
                        "date": entry.get("published") or "",
                        "body_excerpt": summary,
                        "source": "ReliefWeb (RSS)",
                        "url": entry.get("link") or "",
                        "sentiment_score": score,
                        "sentiment_label": "ESCALATORY"
                        if score > 0.2
                        else "DE-ESCALATORY"
                        if score < -0.2
                        else "NEUTRAL",
                        "platform": "reliefweb",
                    }
                )
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
                    logger.info(
                        "SOCMINT ReliefWeb: 403 – appname not approved, falling back to RSS. Register at https://apidoc.reliefweb.int/parameters#appname"
                    )
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
            date_created = (
                date_obj.get("created") or date_obj.get("changed") or "" if isinstance(date_obj, dict) else ""
            )
            src_list = fields.get("source") or []
            source = src_list[0].get("name", "ReliefWeb") if src_list and isinstance(src_list[0], dict) else "ReliefWeb"
            url_link = (
                fields.get("url", "")
                if isinstance(fields.get("url"), str)
                else (fields.get("url", [{}])[0].get("url", "") if isinstance(fields.get("url"), list) else "")
            )
            score = _sentiment(combined)
            results.append(
                {
                    "title": title,
                    "date": date_created,
                    "body_excerpt": body_excerpt,
                    "source": source,
                    "url": url_link,
                    "sentiment_score": score,
                    "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                    "platform": "reliefweb",
                }
            )
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
    texts = [(p.get("text") or p.get("title") or p.get("body_excerpt") or "")[:1000] for p in top_posts]
    all_entities: List[Dict[str, Any]] = []
    try:
        from services.haiku_service import HAIKU_MAX_NER_PER_RUN, batch_ner, is_haiku_failed
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
