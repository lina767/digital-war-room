"""
SOCMINT Agent - LangChain Tool-Calling Agent
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import feedparser
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

TELEGRAM_CHANNELS = {
    "middle_east": ["intelslava", "MiddleEastSpectator", "OSINTdefender"],
    "eastern_europe": ["intelslava", "ukraine_now", "osint_ua"],
    "east_asia": ["OSINTdefender", "intelslava"],
    "africa": ["intelslava", "OSINTdefender"],
}
REDDIT_SUBREDDITS = {
    "middle_east": ["geopolitics", "worldnews", "MiddleEast", "iran"],
    "eastern_europe": ["geopolitics", "worldnews", "ukraine"],
    "east_asia": ["geopolitics", "worldnews", "taiwan"],
    "africa": ["geopolitics", "worldnews", "africa"],
}
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]
ESCALATION_KW = ["attack","strike","missile","war","explosion","killed","military","nuclear","threat","troops","airstrike"]
DE_ESCALATION_KW = ["ceasefire","talks","diplomatic","deal","agreement","peace","negotiate"]

def _region(conflict):
    cl = conflict.lower()
    if any(k in cl for k in ["iran","israel","gaza","yemen","syria"]): return "middle_east"
    if any(k in cl for k in ["ukraine","russia","donbas"]): return "eastern_europe"
    if any(k in cl for k in ["taiwan","china","korea"]): return "east_asia"
    if any(k in cl for k in ["sudan","ethiopia","sahel"]): return "africa"
    return "middle_east"

def _keywords(conflict):
    cl = conflict.lower()
    if "iran" in cl: return ["iran","irgc","tehran","nuclear","khamenei"]
    if "ukraine" in cl: return ["ukraine","russia","kyiv","nato","zelensky"]
    if "israel" in cl or "gaza" in cl: return ["israel","gaza","hamas","idf"]
    if "taiwan" in cl: return ["taiwan","china","pla","strait"]
    return cl.split() or ["conflict"]

def _sentiment(text):
    lower = text.lower()
    s = sum(1 for k in ESCALATION_KW if k in lower) - sum(1 for k in DE_ESCALATION_KW if k in lower)
    return 0.0 if s == 0 else max(-3, min(3, s)) / 3.0

@tool
def scrape_telegram_channels(conflict: str) -> List[Dict[str, Any]]:
    """Scrape public Telegram channels for conflict-related posts."""
    import re
    channels = TELEGRAM_CHANNELS.get(_region(conflict), TELEGRAM_CHANNELS["middle_east"])
    kw = _keywords(conflict)
    async def _fetch(client, ch):
        try:
            resp = await client.get(f"https://t.me/s/{ch}", follow_redirects=True)
            if resp.status_code != 200: return []
            msgs = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', m).strip() for m in msgs]
            results = []
            for text in clean[:10]:
                if len(text) < 20 or not any(k in text.lower() for k in kw): continue
                sc = _sentiment(text)
                results.append({"source": f"telegram:{ch}", "text": text[:300], "sentiment_score": sc,
                    "sentiment_label": "ESCALATORY" if sc > 0.2 else "DE-ESCALATORY" if sc < -0.2 else "NEUTRAL", "platform": "telegram"})
            return results
        except: return []
    async def _run():
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            results = await asyncio.gather(*[_fetch(client, ch) for ch in channels], return_exceptions=True)
            return [p for r in results if isinstance(r, list) for p in r]
    try: return asyncio.run(_run())
    except Exception as e: return [{"error": str(e)}]

@tool
def search_reddit(conflict: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search Reddit for recent conflict-related posts."""
    subreddits = REDDIT_SUBREDDITS.get(_region(conflict), ["geopolitics","worldnews"])
    kw = _keywords(conflict)
    async def _fetch(client, sr):
        try:
            resp = await client.get(f"https://www.reddit.com/r/{sr}/new.json", params={"limit": limit})
            resp.raise_for_status()
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            results = []
            for post in resp.json().get("data", {}).get("children", []):
                p = post.get("data", {})
                created = datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc)
                if created < cutoff: continue
                title = p.get("title", ""); text = p.get("selftext", "")
                combined = f"{title} {text}".lower()
                if not any(k in combined for k in kw): continue
                sc = _sentiment(combined)
                results.append({"source": f"reddit:r/{sr}", "title": title, "text": text[:200],
                    "url": f"https://reddit.com{p.get('permalink','')}", "upvotes": p.get("score", 0),
                    "sentiment_score": sc, "sentiment_label": "ESCALATORY" if sc > 0.2 else "DE-ESCALATORY" if sc < -0.2 else "NEUTRAL",
                    "platform": "reddit", "published_at": created.isoformat()})
            return results
        except: return []
    async def _run():
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "DigitalWarRoom/1.0"}) as client:
            results = await asyncio.gather(*[_fetch(client, sr) for sr in subreddits], return_exceptions=True)
            posts = [p for r in results if isinstance(r, list) for p in r]
            return sorted(posts, key=lambda x: x.get("upvotes", 0), reverse=True)[:20]
    try: return asyncio.run(_run())
    except Exception as e: return [{"error": str(e)}]

@tool
def fetch_rss_feeds(conflict: str) -> List[Dict[str, Any]]:
    """Fetch RSS feeds for conflict-related content."""
    import calendar
    kw = _keywords(conflict)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    results = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = entry.get("title", ""); summary = entry.get("summary", "")
                combined = f"{title} {summary}".lower()
                if not any(k in combined for k in kw): continue
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try: published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
                    except: pass
                if published and published < cutoff: continue
                sc = _sentiment(combined)
                results.append({"source": f"rss:{feed.feed.get('title', url)}", "title": title,
                    "summary": summary[:200], "url": entry.get("link", ""), "sentiment_score": sc,
                    "sentiment_label": "ESCALATORY" if sc > 0.2 else "DE-ESCALATORY" if sc < -0.2 else "NEUTRAL",
                    "platform": "rss", "published_at": published.isoformat() if published else ""})
        except: continue
    return results[:20]

SOCMINT_TOOLS = [scrape_telegram_channels, search_reddit, fetch_rss_feeds]
SOCMINT_SYSTEM = """You are a SOCMINT analyst. Call all three tools, then return ONLY valid JSON:
{"telegram_posts":[...],"reddit_posts":[...],"rss_articles":[...],"total_signals":<n>,"escalatory_count":<n>,"de_escalatory_count":<n>,"overall_sentiment":<-1 to 1>,"socmint_score":<0-100>,"top_signals":["..."],"summary":"..."}"""

def run_socmint_agent(conflict: str) -> Dict[str, Any]:
    """Run SOCMINT agent with LangChain tool-calling."""
    import json
    model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0).bind_tools(SOCMINT_TOOLS)
    messages = [SystemMessage(content=SOCMINT_SYSTEM), HumanMessage(content=f"Monitor social media for conflict: {conflict}")]
    for _ in range(6):
        response = model.invoke(messages)
        messages.append(response)
        if not response.tool_calls:
            try:
                content = response.content
                if isinstance(content, list): content = " ".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
                result = json.loads(content); result["conflict"] = conflict; return result
            except: break
        for tc in response.tool_calls:
            tool_map = {t.name: t for t in SOCMINT_TOOLS}
            fn = tool_map.get(tc["name"])
            if fn:
                messages.append(ToolMessage(content=json.dumps(fn.invoke(tc.get("args",{})), default=str), tool_call_id=tc["id"]))
    return {"conflict": conflict, "telegram_posts": [], "reddit_posts": [], "rss_articles": [],
        "total_signals": 0, "escalatory_count": 0, "de_escalatory_count": 0,
        "overall_sentiment": 0.0, "socmint_score": 30.0, "top_signals": [], "summary": "SOCMINT data unavailable."}
