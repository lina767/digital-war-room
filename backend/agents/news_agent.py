"""
NEWS Agent – LangChain Tool-Calling Agent
Fetches and analyzes conflict-related news articles from NewsAPI, GDELT, and RSS.
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

import feedparser
import httpx
from .llm_factory import get_agent_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

NEWS_API_URL = "https://newsapi.org/v2/everything"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWS_DOMAINS = (
    "reuters.com,apnews.com,bbc.com,aljazeera.com,theguardian.com,"
    "nytimes.com,washingtonpost.com,ft.com,bloomberg.com,politico.com,"
    "foreignpolicy.com,defensenews.com,jpost.com,haaretz.com,irna.ir,"
    "middleeasteye.net,thehill.com"
)

# Vielfältige Quellen: internationale & regionale Medien, Think-Tanks (FDD/LWJ, CSIS, Crisis Group, ECFR, ISW, Bellingcat)
RSS_FEEDS = {
    "iran": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://iranintl.com/en/rss",
        "https://www.rferl.org/api/zpqoyhrhkhrut",  # RFE/RL Iran
        "https://www.middleeasteye.net/rss",
        "https://www.criticalthreats.org/feed",
        "https://www.longwarjournal.org/feed",
        "https://understandingwar.org/rss.xml",  # ISW – Iran Update
        "https://www.bellingcat.com/feed/",  # Bellingcat OSINT
        "https://www.crisisgroup.org/rss/85",  # Crisis Group – Iran
        "https://ecfr.eu/feed/",  # European Council on Foreign Relations
        "https://www.csis.org/rss.xml",  # CSIS (Middle East / Iran analysis)
        "https://www.fdd.org/feed/",  # FDD – Iran reports (if available)
    ],
    "ukraine": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.rferl.org/api/ztqppqhrpmqio",  # RFE/RL Ukraine
        "https://www.kyivpost.com/rss",
        "https://www.middleeasteye.net/rss",
        "https://understandingwar.org/rss.xml",
        "https://www.criticalthreats.org/feed",
        "https://www.longwarjournal.org/feed",
    ],
    "default": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.france24.com/en/rss",
        "https://www.theguardian.com/world/rss",
    ],
}

TITLE_EXCLUDE = ["marathon", "eurovision", "cricket", "bollywood", "sports", "weather"]
ESCALATION_KW = ["attack", "strike", "missile", "war", "explosion", "killed", "military", "nuclear", "threat", "sanctions"]
DE_ESCALATION_KW = ["ceasefire", "talks", "diplomatic", "deal", "agreement", "withdraw", "peace", "negotiate"]


def _build_query(conflict: str) -> str:
    cl = conflict.lower()
    if "iran" in cl:
        return (
            '(Iran OR IRGC OR "Persian Gulf" OR Khamenei OR Rouhani OR "nuclear deal" '
            'OR "Iranian military" OR "US Iran" OR "Israel Iran" OR Hormuz OR "Iranian strike") '
            "AND (attack OR military OR nuclear OR sanctions OR war OR strike OR missile OR deal)"
        )
    if "ukraine" in cl:
        return ('(Ukraine OR Zelensky OR Kyiv OR Donbas) '
                "AND (Russia OR invasion OR NATO OR military OR sanctions)")
    return f'"{conflict}"' if " " in conflict else conflict


def _sentiment(text: str) -> float:
    lower = text.lower()
    score = sum(1 for kw in ESCALATION_KW if kw in lower)
    score -= sum(1 for kw in DE_ESCALATION_KW if kw in lower)
    if score == 0:
        return 0.0
    return max(-3, min(3, score)) / 3.0


def _label(score: float) -> str:
    if score > 0.2:
        return "ESCALATORY"
    if score < -0.2:
        return "DE-ESCALATORY"
    return "NEUTRAL"


# ── Tools ──────────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication (strip trailing slash, lowercase scheme/host)."""
    if not url or not isinstance(url, str):
        return ""
    try:
        p = urlparse(url)
        path = p.path.rstrip("/") or "/"
        return f"{p.scheme.lower()}://{p.netloc.lower()}{path}"
    except Exception:
        return url or ""


SOURCE_WEIGHTS = {"newsapi": 0.5, "gdelt": 0.3, "rss": 0.2}


def _merge_news_results(
    newsapi_list: List[Dict[str, Any]],
    gdelt_list: List[Dict[str, Any]],
    rss_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deduplicate by URL, compute weighted overall_sentiment, top 20 by sentiment_score, source_breakdown."""
    seen: Dict[str, Dict[str, Any]] = {}
    for item in newsapi_list + gdelt_list + rss_list:
        if "error" in item or not item.get("url"):
            continue
        norm = _normalize_url(item.get("url", ""))
        if not norm:
            continue
        if norm in seen:
            continue
        seen[norm] = {**item, "url": item.get("url")}
    articles = list(seen.values())
    articles.sort(key=lambda a: (a.get("sentiment_score") or 0), reverse=True)
    top20 = articles[:20]

    weighted_sum = 0.0
    weight_sum = 0.0
    for a in top20:
        w = SOURCE_WEIGHTS.get(a.get("source_type", "newsapi"), 0.5)
        s = a.get("sentiment_score") or 0.0
        weighted_sum += w * s
        weight_sum += w
    overall_sentiment = weighted_sum / weight_sum if weight_sum else 0.0

    source_breakdown = {"newsapi": 0, "gdelt": 0, "rss": 0}
    for a in top20:
        st = a.get("source_type") or "newsapi"
        if st in source_breakdown:
            source_breakdown[st] += 1

    return {
        "articles": top20,
        "overall_sentiment": round(overall_sentiment, 4),
        "sentiment_label": _label(overall_sentiment),
        "source_breakdown": source_breakdown,
    }


@tool
def search_conflict_news(conflict: str, hours_back: int = 48) -> List[Dict[str, Any]]:
    """Search for recent news articles about a conflict from trusted sources (NewsAPI)."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return [{"error": "NEWS_API_KEY not set"}]

    async def _fetch(hours: int):
        from_date = datetime.now(timezone.utc) - timedelta(hours=hours)
        params = {
            "q": _build_query(conflict),
            "language": "en",
            "sortBy": "relevance",
            "pageSize": 20,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "domains": NEWS_DOMAINS,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NEWS_API_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    try:
        data = asyncio.run(_fetch(hours_back))
        articles = []
        for art in data.get("articles", []):
            title = art.get("title") or ""
            if any(kw in title.lower() for kw in TITLE_EXCLUDE):
                continue
            desc = art.get("description") or ""
            score = _sentiment(f"{title} {desc}")
            source = (art.get("source") or {}).get("name") or ""
            articles.append({
                "title": title,
                "source": source,
                "url": art.get("url"),
                "published_at": art.get("publishedAt"),
                "sentiment_score": score,
                "sentiment_label": _label(score),
                "source_type": "newsapi",
            })
        if not articles and hours_back == 48:
            data = asyncio.run(_fetch(72))
            articles = []
            for art in data.get("articles", []):
                title = art.get("title") or ""
                if any(kw in title.lower() for kw in TITLE_EXCLUDE):
                    continue
                desc = art.get("description") or ""
                score = _sentiment(f"{title} {desc}")
                source = (art.get("source") or {}).get("name") or ""
                articles.append({
                    "title": title,
                    "source": source,
                    "url": art.get("url"),
                    "published_at": art.get("publishedAt"),
                    "sentiment_score": score,
                    "sentiment_label": _label(score),
                    "source_type": "newsapi",
                })
        return articles
    except Exception as e:
        return [{"error": str(e)}]


def _gdelt_article_list(data: Any) -> List[Dict[str, Any]]:
    """Extract list of articles from GDELT API response (multiple possible shapes)."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("articles", "articleList", "results", "docs", "ArticleList"):
        out = data.get(key)
        if isinstance(out, list):
            return out
    return []


@tool
def search_gdelt_news(conflict: str) -> List[Dict[str, Any]]:
    """Search GDELT for conflict news - covers 100+ languages, 65k+ sources worldwide."""
    query = _build_query(conflict).replace('"', ' ').replace("(", "").replace(")", "").strip()
    if not query:
        query = conflict

    async def _fetch():
        # GDELT accepts timespan as "48H" or "2d"; format=json for JSON response
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": 25,
            "format": "json",
            "timespan": "48H",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(GDELT_URL, params=params)
            resp.raise_for_status()
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct and "javascript" not in ct:
                return []
            return resp.json()

    try:
        data = asyncio.run(_fetch())
        raw_list = _gdelt_article_list(data)
        articles = []
        for art in raw_list:
            if not isinstance(art, dict):
                continue
            url = art.get("url") or art.get("url_mobile") or art.get("socialimage")
            title = (art.get("title") or art.get("snippet") or "").strip()
            lang = (art.get("language") or art.get("sourcecountry") or "").lower()
            # Include if English or language unknown; skip only when clearly non-English
            if lang and "en" not in lang and lang != "eng":
                continue
            if not url:  # need url for dedupe and linking
                continue
            score = _sentiment(title)
            articles.append({
                "title": (title[:500] if title else "(No title)"),
                "source": art.get("domain") or art.get("sourcecountry") or "GDELT",
                "url": url or "",
                "published_at": art.get("seendate"),
                "sentiment_score": score,
                "sentiment_label": _label(score),
                "source_type": "gdelt",
            })
        return articles[:25]
    except Exception as e:
        return [{"error": str(e)}]


def _rss_feeds_for_conflict(conflict: str) -> List[str]:
    cl = conflict.lower()
    if "iran" in cl:
        return RSS_FEEDS["iran"]
    if "ukraine" in cl or "russia" in cl:
        return RSS_FEEDS["ukraine"]
    return RSS_FEEDS["default"]


@tool
def search_rss_feeds(conflict: str) -> List[Dict[str, Any]]:
    """Fetch conflict-specific RSS feeds from think tanks and regional outlets."""
    feeds = _rss_feeds_for_conflict(conflict)
    keywords = []
    cl = conflict.lower()
    if "iran" in cl:
        keywords = ["iran", "irgc", "tehran", "nuclear", "khamenei", "persian gulf", "iranian"]
    elif "ukraine" in cl or "russia" in cl:
        keywords = ["ukraine", "russia", "kyiv", "donbas", "nato", "zelensky", "invasion"]
    else:
        keywords = [w for w in conflict.split() if len(w) > 2][:5] or ["conflict", "military"]
    results = []
    for feed_url in feeds:
        try:
            parsed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": "Mozilla/5.0 (compatible; NewsAgent/1.0)"},
            )
            for entry in getattr(parsed, "entries", [])[:15]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link") or ""
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                if not link:
                    continue
                text = f"{title} {summary}".lower()
                if not any(kw in text for kw in keywords):
                    continue
                score = _sentiment(f"{title} {summary}")
                source = (parsed.feed.get("title") or feed_url) if getattr(parsed, "feed", None) else feed_url
                results.append({
                    "title": title[:500],
                    "source": source,
                    "url": link,
                    "published_at": entry.get("published") or entry.get("updated"),
                    "sentiment_score": score,
                    "sentiment_label": _label(score),
                    "source_type": "rss",
                })
        except Exception:
            continue
    return results


# ── Rule-based NEWS multi-agent building blocks ─────────────────────────────

def _run_newsapi_source_agent(conflict: str, hours_back: int = 48) -> Dict[str, Any]:
    """Source agent: NewsAPI-only view of the conflict."""
    raw = search_conflict_news.invoke({"conflict": conflict, "hours_back": hours_back})
    articles = [
        a for a in (raw if isinstance(raw, list) else [])
        if isinstance(a, dict) and "error" not in a
    ]
    return {
        "source": "newsapi",
        "articles": articles,
        "count": len(articles),
    }


def _run_gdelt_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: GDELT-only view of the conflict."""
    raw = search_gdelt_news.invoke({"conflict": conflict})
    articles = [
        a for a in (raw if isinstance(raw, list) else [])
        if isinstance(a, dict) and "error" not in a
    ]
    return {
        "source": "gdelt",
        "articles": articles,
        "count": len(articles),
    }


def _run_rss_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: curated RSS/think-tank/OSINT feeds."""
    raw = search_rss_feeds.invoke({"conflict": conflict})
    articles = [
        a for a in (raw if isinstance(raw, list) else [])
        if isinstance(a, dict) and "error" not in a
    ]
    return {
        "source": "rss",
        "articles": articles,
        "count": len(articles),
    }


def _run_news_fusion_agent(
    newsapi_res: Dict[str, Any],
    gdelt_res: Dict[str, Any],
    rss_res: Dict[str, Any],
) -> Dict[str, Any]:
    """Fusion agent: dedupe + global sentiment/score across all sources."""
    merged = _merge_news_results(
        newsapi_list=newsapi_res.get("articles", []),
        gdelt_list=gdelt_res.get("articles", []),
        rss_list=rss_res.get("articles", []),
    )
    articles = merged.get("articles", [])
    overall = merged.get("overall_sentiment", 0.0)
    label = merged.get("sentiment_label", "NEUTRAL")
    breakdown = merged.get("source_breakdown", {"newsapi": 0, "gdelt": 0, "rss": 0})

    score = 50.0
    if overall > 0.5:
        score += 20
    elif overall > 0.2:
        score += 10
    elif overall < -0.2:
        score -= 15
    if len(articles) > 10:
        score += 10
    score = max(0, min(100, score))

    top_sources = list(
        dict.fromkeys(a.get("source") or "" for a in articles[:10] if a.get("source"))
    )

    return {
        "articles": articles,
        "overall_sentiment": overall,
        "sentiment_label": label,
        "source_breakdown": breakdown,
        "news_score": score,
        "top_sources": top_sources,
    }


def _run_escalation_headline_agent(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Meta-agent: focuses on clearly escalatory headlines to provide an explicit escalation signal.
    Uses the existing sentiment labels as discrete triggers.
    """
    escalatory = [a for a in articles if (a.get("sentiment_label") or "").upper() == "ESCALATORY"]
    # Simple heuristic: 0–1 score based on number of escalatory headlines (saturates at 10)
    escalation_score = min(1.0, len(escalatory) / 10.0) if escalatory else 0.0
    return {
        "escalation_headlines": escalatory[:10],
        "escalation_score": escalation_score,
    }


# ── Rule-based tool chain orchestrator (fixed order; no LLM) ────────────────

def _run_rule_based_news(conflict: str) -> Dict[str, Any]:
    """
    Execute NEWS as a small, rule-based multi-agent system:

    1. Three source agents (NewsAPI, GDELT, RSS) fetch their respective views.
    2. A fusion agent deduplicates and computes global sentiment/score.
    3. A meta-agent focuses on escalatory headlines for an explicit escalation signal.

    The overall return format remains compatible with existing callers of run_news_agent.
    """
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_newsapi = executor.submit(_run_newsapi_source_agent, conflict)
            fut_gdelt = executor.submit(_run_gdelt_source_agent, conflict)
            fut_rss = executor.submit(_run_rss_source_agent, conflict)
            newsapi_res = fut_newsapi.result(timeout=35)
            gdelt_res = fut_gdelt.result(timeout=35)
            rss_res = fut_rss.result(timeout=35)

        fusion = _run_news_fusion_agent(newsapi_res, gdelt_res, rss_res)
        articles = fusion.get("articles", [])

        escalation_meta = _run_escalation_headline_agent(articles)

        return {
            "conflict": conflict,
            "articles": fusion.get("articles", []),
            "overall_sentiment": fusion.get("overall_sentiment", 0.0),
            "sentiment_label": fusion.get("sentiment_label", "NEUTRAL"),
            "top_sources": fusion.get("top_sources", []),
            "news_score": fusion.get("news_score", 50.0),
            "summary": (
                "News (rule-based multi-agent): "
                f"{fusion.get('source_breakdown', {}).get('newsapi', 0)} NewsAPI, "
                f"{fusion.get('source_breakdown', {}).get('gdelt', 0)} GDELT, "
                f"{fusion.get('source_breakdown', {}).get('rss', 0)} RSS. "
                f"Sentiment: {fusion.get('sentiment_label', 'NEUTRAL')}. "
                f"Escalation score: {escalation_meta.get('escalation_score', 0.0):.2f}."
            ),
            "source_breakdown": fusion.get("source_breakdown", {"newsapi": 0, "gdelt": 0, "rss": 0}),
            "escalation_headlines": escalation_meta.get("escalation_headlines", []),
            "escalation_score": escalation_meta.get("escalation_score", 0.0),
        }
    except Exception:
        pass
    return {
        "conflict": conflict,
        "articles": [],
        "overall_sentiment": 0.0,
        "sentiment_label": "NEUTRAL",
        "top_sources": [],
        "news_score": 50.0,
        "summary": "NEWS data unavailable.",
        "source_breakdown": {"newsapi": 0, "gdelt": 0, "rss": 0},
    }


# ── Agent ──────────────────────────────────────────────────────────────────

NEWS_TOOLS = [search_conflict_news, search_gdelt_news, search_rss_feeds]

NEWS_SYSTEM = """You are a NEWS/OSINT analyst monitoring open-source media.
Your job: fetch news from all three tools (NewsAPI, GDELT, RSS), combine and analyze.

You MUST call all three tools: search_conflict_news, search_gdelt_news, search_rss_feeds.
Then combine results as follows:
- Deduplicate by URL (keep first occurrence).
- Compute overall_sentiment as weighted average: NewsAPI weight 0.5, GDELT 0.3, RSS 0.2.
- Return top 20 articles total, sorted by sentiment_score descending.
- Add source_breakdown: {"newsapi": N, "gdelt": N, "rss": N} with article counts per source.

Scoring rules for news_score (0-100):
- Base: 50
- Overall sentiment > 0.5 (very escalatory): +20
- Overall sentiment 0.2-0.5: +10
- Overall sentiment < -0.2 (de-escalatory): -15
- More than 10 recent articles: +10
- Clamp to [0, 100]

Return ONLY valid JSON (no markdown, no explanation):
{
  "articles": [...],
  "overall_sentiment": <number -1 to 1>,
  "sentiment_label": "NEUTRAL|ESCALATORY|DE-ESCALATORY",
  "top_sources": ["source1", ...],
  "news_score": <number>,
  "summary": "<1-2 sentence summary>",
  "source_breakdown": {"newsapi": N, "gdelt": N, "rss": N}
}"""


def run_news_agent(conflict: str) -> Dict[str, Any]:
    """Run NEWS: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    import json
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_news(conflict)

    model = get_agent_model(NEWS_TOOLS)

    messages = [
        SystemMessage(content=NEWS_SYSTEM),
        HumanMessage(content=f"Analyze news coverage for conflict: {conflict}"),
    ]

    for _ in range(5):
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
            tool_map = {t.name: t for t in NEWS_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                args = tc.get("args", {})
                if "conflict" not in args:
                    args["conflict"] = conflict
                result = tool_fn.invoke(args)
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    # Fallback: same fixed tool chain as rule-based mode
    return _run_rule_based_news(conflict)

