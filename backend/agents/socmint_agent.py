"""
SOCMINT Agent – LangChain Tool-Calling Agent
Monitors Telegram, X/Twitter (Nitter), Reddit, RSS, and ReliefWeb for conflict signals.
"""
import asyncio
import re
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import feedparser
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

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
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
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
        "https://www.criticalthreats.org/feed",
        "https://www.longwarjournal.org/feed",
        "https://iranintl.com/en/rss",
        "https://www.rferl.org/api/zpqoyhrhkhrut",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://understandingwar.org/rss.xml",
    ],
    "eastern_europe": [
        "https://understandingwar.org/rss.xml",
        "https://www.rferl.org/api/epruslt",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.kyivpost.com/rss",
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
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria"]):
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
    if "iran" in cl:
        return ["iran", "irgc", "tehran", "nuclear", "khamenei", "persian gulf"]
    if "ukraine" in cl:
        return ["ukraine", "russia", "kyiv", "donbas", "nato", "zelensky"]
    if "israel" in cl or "gaza" in cl:
        return ["israel", "gaza", "hamas", "idf", "netanyahu", "west bank"]
    if "taiwan" in cl:
        return ["taiwan", "china", "pla", "strait", "beijing", "taipei"]
    words = cl.split()
    return words if words else ["conflict", "military"]


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
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
            resp = await client.get(url, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; SOCMINT/1.0)"})
            if resp.status_code != 200:
                return []
            html = resp.text
            messages = _extract_telegram_messages(html)
            clean = [m for m in messages if m and len(m) >= 10]
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
        except Exception:
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
        return asyncio.run(_run())
    except Exception as e:
        return [{"error": str(e)}]


@tool
def scrape_twitter_nitter(conflict: str) -> List[Dict[str, Any]]:
    """
    Scrape conflict-relevant Twitter/X accounts via public Nitter instances.
    No API key required. Falls back through multiple Nitter instances.
    """
    region = _conflict_to_region(conflict)
    keywords = _conflict_keywords(conflict)
    accounts = CONFLICT_TWITTER_ACCOUNTS.get(region, CONFLICT_TWITTER_ACCOUNTS["middle_east"])

    async def _fetch_account(client: httpx.AsyncClient, account: str) -> List[Dict[str, Any]]:
        for base in NITTER_INSTANCES:
            try:
                url = f"{base}/{account}"
                resp = await client.get(url, follow_redirects=True, timeout=12.0)
                if resp.status_code != 200:
                    continue
                html = resp.text
                # Nitter tweet content: common class names
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
                        score = _sentiment(text)
                        results.append({
                            "source": f"twitter:{account}",
                            "text": text[:300],
                            "sentiment_score": score,
                            "sentiment_label": "ESCALATORY" if score > 0.2 else "DE-ESCALATORY" if score < -0.2 else "NEUTRAL",
                            "platform": "twitter",
                            "account": account,
                        })
                    return results
            except Exception:
                continue
        return []

    async def _run():
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SOCMINT/1.0)"}) as client:
            tasks = [_fetch_account(client, acc) for acc in accounts[:6]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            posts = []
            for r in results:
                if isinstance(r, list):
                    posts.extend(r)
            posts.sort(key=lambda x: x.get("sentiment_score", 0), reverse=True)
            return posts[:15]

    try:
        return asyncio.run(_run())
    except Exception as e:
        return [{"error": str(e)}]


@tool
def search_reddit(conflict: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Reddit for recent conflict-related posts using public JSON API.
    No API key required.
    """
    region = _conflict_to_region(conflict)
    subreddits = REDDIT_SUBREDDITS.get(region, ["geopolitics", "worldnews"])
    keywords = _conflict_keywords(conflict)

    async def _fetch_subreddit(client: httpx.AsyncClient, subreddit: str) -> List[Dict[str, Any]]:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json"
            resp = await client.get(url, params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            results = []
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
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

    async def _run():
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "DigitalWarRoom/1.0 (conflict analysis research)"}
        ) as client:
            tasks = [_fetch_subreddit(client, sr) for sr in subreddits]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            posts = []
            for r in results:
                if isinstance(r, list):
                    posts.extend(r)
            posts.sort(key=lambda x: x.get("upvotes", 0), reverse=True)
            return posts[:20]

    try:
        return asyncio.run(_run())
    except Exception as e:
        return [{"error": str(e)}]


@tool
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


RELIEFWEB_APPNAME = "digital-war-room"
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


@tool
def fetch_reliefweb_reports(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent conflict reports from ReliefWeb API v2.
    Free, no API key, covers humanitarian and conflict events globally.
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
        return asyncio.run(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── Agent ──────────────────────────────────────────────────────────────────

SOCMINT_TOOLS = [
    scrape_telegram_channels,
    scrape_twitter_nitter,
    search_reddit,
    fetch_rss_feeds,
    fetch_reliefweb_reports,
]

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
    """Run SOCMINT agent with LangChain tool-calling."""
    import json
    model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0).bind_tools(SOCMINT_TOOLS)

    messages = [
        SystemMessage(content=SOCMINT_SYSTEM),
        HumanMessage(content=f"Monitor social media and open sources for conflict: {conflict}"),
    ]

    for _ in range(6):
        response = model.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            try:
                content = response.content
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                result = json.loads(content)
                result["conflict"] = conflict
                return result
            except Exception:
                break

        for tc in response.tool_calls:
            tool_map = {t.name: t for t in SOCMINT_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                args = dict(tc.get("args", {}))
                if "conflict" not in args:
                    args["conflict"] = conflict
                result = tool_fn.invoke(args)
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    # Fallback: call all 5 tools directly and aggregate
    try:
        telegram = [p for p in (scrape_telegram_channels.invoke({"conflict": conflict}) or []) if isinstance(p, dict) and "error" not in p]
        twitter = [p for p in (scrape_twitter_nitter.invoke({"conflict": conflict}) or []) if isinstance(p, dict) and "error" not in p]
        reddit = [p for p in (search_reddit.invoke({"conflict": conflict}) or []) if isinstance(p, dict) and "error" not in p]
        rss = [p for p in (fetch_rss_feeds.invoke({"conflict": conflict}) or []) if isinstance(p, dict) and "error" not in p]
        reliefweb = [p for p in (fetch_reliefweb_reports.invoke({"conflict": conflict}) or []) if isinstance(p, dict) and "error" not in p]

        all_posts = telegram + twitter + reddit + rss + reliefweb
        escalatory = sum(1 for p in all_posts if p.get("sentiment_label") == "ESCALATORY")
        de_esc = sum(1 for p in all_posts if p.get("sentiment_label") == "DE-ESCALATORY")
        sent_sum = sum(p.get("sentiment_score", 0) for p in all_posts)
        overall_sentiment = (sent_sum / len(all_posts)) if all_posts else 0.0

        base = 30.0
        # Verified OSINT Twitter: +8 per escalatory post
        twitter_esc = sum(1 for p in twitter if p.get("sentiment_label") == "ESCALATORY" and p.get("account") in ("sentdefcon", "OSINTdefender"))
        base += min(50, twitter_esc * 8)
        # ReliefWeb: +10 each (max +20)
        base += min(20, len(reliefweb) * 10)
        # Telegram escalatory channels: +6 per channel with escalatory content (max +24)
        telegram_channels_with_esc = len(set(p.get("source", "") for p in telegram if p.get("sentiment_label") == "ESCALATORY"))
        base += min(24, telegram_channels_with_esc * 6)
        # Other escalatory: +3 each (cap)
        base += min(30, (escalatory - twitter_esc) * 3)
        base -= de_esc * 2
        reddit_high = sum(1 for p in reddit if p.get("upvotes", 0) > 1000)
        base += min(15, reddit_high * 5)
        score = max(0.0, min(100.0, base))

        top_signals = []
        for p in sorted(all_posts, key=lambda x: (x.get("sentiment_score", 0), x.get("upvotes", 0)), reverse=True)[:5]:
            t = p.get("text") or p.get("title") or p.get("body_excerpt") or ""
            if t:
                top_signals.append(t[:120] + ("..." if len(t) > 120 else ""))

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
            "summary": f"SOCMINT: {len(all_posts)} signals ({escalatory} escalatory, {de_esc} de-escalatory). Score {score:.0f}.",
        }
    except Exception:
        pass
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
    }