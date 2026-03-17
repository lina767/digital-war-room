"""
NEWS Agent.
Fetches and analyzes conflict-related news articles from NewsAPI, GDELT, RSS,
and optionally NewsData.io and GNews when NEWSDATA_API_KEY / GNEWS_API_KEY are set.

Multi-API strategy: one request per API per run (respects 100/day NewsAPI & GNews,
200/day NewsData). Same query via _build_query(conflict); merge, URL-dedupe, then
HF semantic dedup and cross-encoder ranking. See docs/API-KEYS.md "News-APIs gemeinsam einsetzen".
"""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .context import AgentContext
from urllib.parse import urlparse

import feedparser
import httpx

from .config import NEWS_MAX_PER_SOURCE, NEWS_TOP_K, USER_AGENT
from .domain_runner import run_domain_with_analysts
from .health_registry import get_health_registry
from .llm import run_agent_with_fallback
from .utils import (
    AgentMetadata,
    SourceResult,
    compute_confidence_from_sources,
    run_async,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

NEWS_API_URL = "https://newsapi.org/v2/everything"
NEWSDATA_LATEST_URL = "https://newsdata.io/api/1/latest"
GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"
# GDELT DOC 2.0 API (fulltext, artlist); overview: https://www.gdeltproject.org/data.html
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FOREIGN_POLICY_IRAN_PROJECT_URL = "https://foreignpolicy.com/projects/iran-israel-conflict-news-nuclear-sites-proxies/"
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
        "https://www.rferl.org/api/zpqoyhrhkhrut",  # RFE/RL Iran (EN)
        "https://www.middleeasteye.net/rss",
        "https://www.criticalthreats.org/feed",
        "https://www.longwarjournal.org/feed",
        "https://understandingwar.org/rss.xml",  # ISW – Iran Update
        "https://www.bellingcat.com/feed/",  # Bellingcat OSINT
        "https://www.crisisgroup.org/rss/85",  # Crisis Group – Iran
        "https://ecfr.eu/feed/",  # European Council on Foreign Relations
        "https://www.csis.org/rss.xml",  # CSIS (Middle East / Iran analysis)
        "https://www.fdd.org/feed/",  # FDD – Iran reports (if available)
        # Farsi/Persian-language Iran-focused feeds
        "https://iranintl.com/fa/rss",  # Iran International (FA)
        "https://www.radiofarda.com/api/zkqopekqqop_ztql",  # RFE/RL Radio Farda (FA)
        "https://www.bbc.com/persian/index.xml",  # BBC Persian
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
    "sanctions",
]
DE_ESCALATION_KW = ["ceasefire", "talks", "diplomatic", "deal", "agreement", "withdraw", "peace", "negotiate"]

# Farsi/Persian escalation keywords for sentiment analysis
ESCALATION_KW_FA = [
    "حمله",
    "موشک",
    "جنگ",
    "انفجار",
    "کشته",
    "نظامی",
    "هسته‌ای",
    "تهدید",
    "تحریم",
]
DE_ESCALATION_KW_FA = [
    "آتش‌بس",
    "توافق",
    "مذاکره",
    "صلح",
    "گفتگو",
    "عقب‌نشینی",
]

# Chokepoint tagging for CHOKEPOINT agent (single place for NLP logic)
CHOKEPOINT_KEYWORDS: Dict[str, List[str]] = {
    "Strait of Hormuz": ["hormuz", "hormus", "persian gulf", "irgc", "strait of hormuz"],
    "Bab el-Mandeb": ["mandeb", "bab el", "bab al-mandab", "houthi", "red sea", "bab el-mandeb"],
    "Suez Canal": ["suez", "suez canal"],
}
DISRUPTION_VERBS = [
    "blockade",
    "blockaded",
    "halt",
    "halted",
    "suspend",
    "suspended",
    "close",
    "closed",
    "shut",
    "shut down",
    "no transit",
    "reroute",
    "rerouted",
    "cape of good hope",
    "disrupt",
    "disrupted",
    "restricted",
    "closure",
]


def _tag_chokepoint(article: Dict[str, Any]) -> Dict[str, Any]:
    """Set chokepoint_tags and is_disruption on article for CHOKEPOINT agent consumption."""
    title = (article.get("title") or "").lower()
    url = (article.get("url") or "").lower()
    text = f"{title} {url}"
    tags: List[str] = []
    for cp_name, keywords in CHOKEPOINT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                tags.append(cp_name)
                break
        else:
            if cp_name == "Strait of Hormuz" and re.search(r"iran.*strait|strait.*iran", text):
                tags.append(cp_name)
    has_disruption_verb = any(v in text for v in DISRUPTION_VERBS)
    article["chokepoint_tags"] = list(dict.fromkeys(tags))
    article["is_disruption"] = bool(tags and has_disruption_verb)
    return article


def _build_query(conflict: str) -> str:
    cl = conflict.lower()
    if "iran" in cl:
        return (
            '(Iran OR IRGC OR "Persian Gulf" OR Khamenei OR Rouhani OR "nuclear deal" '
            'OR "Iranian military" OR "US Iran" OR "Israel Iran" OR Hormuz OR "Iranian strike" '
            "OR Hezbollah OR Houthi OR Houthis OR IDF OR Yemen OR Lebanon) "
            "AND (attack OR military OR nuclear OR sanctions OR war OR strike OR missile OR deal)"
        )
    if "ukraine" in cl:
        return "(Ukraine OR Zelensky OR Kyiv OR Donbas) AND (Russia OR invasion OR NATO OR military OR sanctions)"
    return f'"{conflict}"' if " " in conflict else conflict


def _sentiment_keyword(text: str) -> float:
    """Fallback: keyword-based sentiment when Haiku is unavailable or over limit."""
    lower = text.lower()
    score = sum(1 for kw in ESCALATION_KW if kw in lower)
    score -= sum(1 for kw in DE_ESCALATION_KW if kw in lower)
    # Farsi sentiment: work on original text (no lowercasing needed for non-Latin)
    score += sum(1 for kw in ESCALATION_KW_FA if kw in text)
    score -= sum(1 for kw in DE_ESCALATION_KW_FA if kw in text)
    if score == 0:
        return 0.0
    return max(-3, min(3, score)) / 3.0


def _label(score: float) -> str:
    if score > 0.2:
        return "ESCALATORY"
    if score < -0.2:
        return "DE-ESCALATORY"
    return "NEUTRAL"


def _label_from_haiku(haiku_label: str) -> str:
    """Map Haiku sentiment label (positive/negative/neutral) to escalation label."""
    if not haiku_label:
        return "NEUTRAL"
    lbl = haiku_label.lower().strip()
    if lbl == "negative":
        return "ESCALATORY"  # negative news (violence, threat) = escalation
    if lbl == "positive":
        return "DE-ESCALATORY"  # positive news (peace, deal) = de-escalation
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


SOURCE_WEIGHTS = {"newsapi": 0.35, "gdelt": 0.25, "rss": 0.2, "newsdata": 0.1, "gnews": 0.1}


# Max articles per source in top-N so one outlet (e.g. Al Jazeera) doesn't dominate. Override via env.


def _normalize_source_for_cap(article: Dict[str, Any]) -> str:
    """Normalize source name for per-source capping (avoid one outlet dominating)."""
    src = (article.get("source") or "").strip() or "unknown"
    if src.startswith("http"):
        return urlparse(src).netloc or src
    # Common feed titles → domain-like key
    lower = src.lower()
    if "al jazeera" in lower:
        return "aljazeera.com"
    if "bbc" in lower:
        return "bbc.com"
    if "reuters" in lower:
        return "reuters.com"
    if "guardian" in lower:
        return "theguardian.com"
    return src[:50]


def _apply_source_cap(articles: List[Dict[str, Any]], top_k: int, max_per_source: int) -> List[Dict[str, Any]]:
    """Keep relevance order but cap articles per source so the list stays diverse."""
    if max_per_source <= 0 or top_k <= 0:
        return articles[:top_k]
    counts: Dict[str, int] = {}
    result: List[Dict[str, Any]] = []
    for a in articles:
        if len(result) >= top_k:
            break
        src = _normalize_source_for_cap(a)
        if counts.get(src, 0) >= max_per_source:
            continue
        result.append(a)
        counts[src] = counts.get(src, 0) + 1
    return result


def _merge_news_results(
    newsapi_list: List[Dict[str, Any]],
    gdelt_list: List[Dict[str, Any]],
    rss_list: List[Dict[str, Any]],
    conflict: str = "",
    newsdata_list: Optional[List[Dict[str, Any]]] = None,
    gnews_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Deduplicate by URL, then semantically, rank by relevance, apply per-source cap, compute weighted overall_sentiment, source_breakdown."""
    seen: Dict[str, Dict[str, Any]] = {}
    all_items = newsapi_list + gdelt_list + rss_list + (newsdata_list or []) + (gnews_list or [])
    for item in all_items:
        if "error" in item or not item.get("url"):
            continue
        norm = _normalize_url(item.get("url", ""))
        if not norm:
            continue
        if norm in seen:
            continue
        seen[norm] = {**item, "url": item.get("url")}
    articles = list(seen.values())

    # Semantic dedup + cross-encoder ranking (graceful: falls back to sentiment sort)
    _hf_available = False
    try:
        from services.hf_service import _get_ranking_query, deduplicate_items, rank_by_relevance

        _hf_available = True
    except Exception:
        pass

    if _hf_available:
        try:
            articles = run_async(
                deduplicate_items(
                    articles,
                    text_key="title",
                    threshold=0.92,
                    source="news",
                    conflict=conflict,
                )
            )
        except Exception as e:
            logger.debug("HF semantic dedup failed: %s", e)

    if _hf_available and conflict:
        try:
            query = _get_ranking_query(conflict)
            texts = [((a.get("title") or "") + " " + (a.get("summary") or "")).strip()[:512] for a in articles]
            if texts:
                ranked = run_async(rank_by_relevance(query, texts, top_k=NEWS_TOP_K * 2))  # rank more, then cap
                articles = [articles[i] for i, _ in ranked if i < len(articles)]
        except Exception as e:
            logger.debug("HF cross-encoder ranking failed: %s", e)
            articles.sort(key=lambda a: a.get("sentiment_score") or 0, reverse=True)
            articles = articles[: NEWS_TOP_K * 2]
    else:
        articles.sort(key=lambda a: a.get("sentiment_score") or 0, reverse=True)
        articles = articles[: NEWS_TOP_K * 2]

    # Per-source cap so one outlet (e.g. Al Jazeera) doesn't dominate the top list
    top20 = _apply_source_cap(articles, top_k=NEWS_TOP_K, max_per_source=NEWS_MAX_PER_SOURCE)
    for a in top20:
        _tag_chokepoint(a)

    # Replace keyword sentiment with Haiku batch_sentiment when available (budget/limits apply)
    try:
        from services.haiku_service import batch_sentiment

        texts = [
            ((a.get("title") or "") + " " + (a.get("summary") or a.get("description") or "")).strip()[:2000]
            for a in top20
        ]
        if texts:
            haiku_results = run_async(batch_sentiment(texts))
            if haiku_results and not all(r is None for r in haiku_results):
                for a, res in zip(top20, haiku_results, strict=True):
                    if res is not None and isinstance(res, dict):
                        # For conflict: Haiku "negative" (violence/threat) = escalation = positive score
                        score = float(res.get("score", 0))
                        a["sentiment_score"] = -score
                        a["sentiment_label"] = _label_from_haiku(res.get("label", ""))
                    # else: keep existing keyword-based sentiment from fetcher
    except Exception as e:
        logger.debug("NEWS Haiku batch_sentiment skipped: %s", e)

    weighted_sum = 0.0
    weight_sum = 0.0
    for a in top20:
        w = SOURCE_WEIGHTS.get(a.get("source_type", "newsapi"), 0.5)
        s = a.get("sentiment_score") or 0.0
        weighted_sum += w * s
        weight_sum += w
    overall_sentiment = weighted_sum / weight_sum if weight_sum else 0.0

    source_breakdown = {"newsapi": 0, "gdelt": 0, "rss": 0, "newsdata": 0, "gnews": 0}
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


def search_conflict_news(conflict: str, hours_back: int = 48) -> List[Dict[str, Any]]:
    """Search for recent news articles about a conflict from trusted sources (NewsAPI).
    Free tier: 100 requests/day (no extra requests); articles have 24h delay; search up to 1 month.
    One request per call to stay within daily limit."""
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
            if resp.status_code == 429:
                return {"articles": [], "_rate_limited": True}
            if resp.status_code == 426:
                return {"articles": [], "_rate_limited": True}
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "error" and "rateLimited" in (data.get("code") or ""):
                return {"articles": [], "_rate_limited": True}
            return data

    try:
        data = run_async(_fetch(hours_back))
        if data.get("_rate_limited"):
            logger.warning("NewsAPI: rate limited (free tier: 100 req/day). Wait or upgrade plan.")
            return [{"error": "NewsAPI rate limited (free tier: 100 req/day)"}]
        articles = []
        for art in data.get("articles", []):
            title = art.get("title") or ""
            if any(kw in title.lower() for kw in TITLE_EXCLUDE):
                continue
            desc = art.get("description") or ""
            score = _sentiment_keyword(f"{title} {desc}")
            source = (art.get("source") or {}).get("name") or ""
            articles.append(
                {
                    "title": title,
                    "source": source,
                    "url": art.get("url"),
                    "published_at": art.get("publishedAt"),
                    "sentiment_score": score,
                    "sentiment_label": _label(score),
                    "language": "en",
                    "source_type": "newsapi",
                }
            )
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


def search_gdelt_news(conflict: str) -> List[Dict[str, Any]]:
    """GDELT news disabled (API unreliable). Returns empty list for backward compatibility."""
    return []


def search_newsdata_news(conflict: str) -> List[Dict[str, Any]]:
    """Search NewsData.io latest endpoint. Free: 200 credits/day, max 10 articles/request.
    Uses q, language, optional country (Location filter). One request per call to conserve credits."""
    api_key = os.getenv("NEWSDATA_API_KEY")
    if not api_key:
        return []

    query = (_build_query(conflict) or conflict).strip()[:512]
    params = {
        "apikey": api_key,
        "q": query or "conflict",
        "language": "en",
        "size": 10,
    }
    # Optional Location filter: country codes for conflict (reduces noise, same credit cost)
    cl = conflict.lower()
    if "iran" in cl or "israel" in cl:
        params["country"] = "ir,il,us"
    elif "ukraine" in cl or "russia" in cl:
        params["country"] = "ua,ru,us"

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NEWSDATA_LATEST_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    try:
        data = run_async(_fetch())
        if data.get("status") == "error":
            return [{"error": data.get("message", "NewsData API error")}]
        results = data.get("results") or []
        articles = []
        for art in results:
            if not isinstance(art, dict):
                continue
            title = (art.get("title") or "").strip()
            link = art.get("link") or ""
            if not link:
                continue
            desc = (art.get("description") or "").strip()
            score = _sentiment_keyword(f"{title} {desc}")
            articles.append(
                {
                    "title": title[:500] if title else "(No title)",
                    "source": art.get("source_name") or "NewsData",
                    "url": link,
                    "published_at": art.get("pubDate"),
                    "description": desc[:1000] if desc else "",
                    "sentiment_score": score,
                    "sentiment_label": _label(score),
                    "language": (art.get("language") or "en").lower(),
                    "source_type": "newsdata",
                }
            )
        return articles[:10]
    except Exception as e:
        return [{"error": str(e)}]


def search_gnews_news(conflict: str) -> List[Dict[str, Any]]:
    """Search GNews API (gnews.io). Free: 100 requests/day. One request per call to stay within limit."""
    api_key = os.getenv("GNEWS_API_KEY")
    if not api_key:
        return []

    query = (_build_query(conflict) or conflict).strip()[:200]  # GNews max 200 chars for q
    params = {
        "apikey": api_key,
        "q": query or "conflict",
        "lang": "en",
        "max": 10,
    }
    cl = conflict.lower()
    if "iran" in cl or "israel" in cl:
        params["country"] = "ir"
    elif "ukraine" in cl or "russia" in cl:
        params["country"] = "ua"

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(GNEWS_SEARCH_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    try:
        data = run_async(_fetch())
        articles_raw = data.get("articles") or []
        articles = []
        for art in articles_raw:
            if not isinstance(art, dict):
                continue
            title = (art.get("title") or "").strip()
            url = art.get("url") or ""
            if not url:
                continue
            desc = (art.get("description") or art.get("content") or "").strip()
            score = _sentiment_keyword(f"{title} {desc}")
            source = art.get("source") or {}
            source_name = source.get("name", "GNews") if isinstance(source, dict) else "GNews"
            articles.append(
                {
                    "title": title[:500] if title else "(No title)",
                    "source": source_name,
                    "url": url,
                    "published_at": art.get("publishedAt"),
                    "description": desc[:1000] if desc else "",
                    "sentiment_score": score,
                    "sentiment_label": _label(score),
                    "language": "en",
                    "source_type": "gnews",
                }
            )
        return articles[:10]
    except Exception as e:
        return [{"error": str(e)}]


def _rss_feeds_for_conflict(conflict: str) -> List[str]:
    cl = conflict.lower()
    if "iran" in cl:
        return RSS_FEEDS["iran"]
    if "ukraine" in cl or "russia" in cl:
        return RSS_FEEDS["ukraine"]
    return RSS_FEEDS["default"]


def search_rss_feeds(conflict: str) -> List[Dict[str, Any]]:
    """Fetch conflict-specific RSS feeds from think tanks and regional outlets."""
    feeds = _rss_feeds_for_conflict(conflict)
    keywords_en: List[str] = []
    keywords_fa: List[str] = []
    cl = conflict.lower()
    if "iran" in cl:
        keywords_en = [
            "iran",
            "irgc",
            "tehran",
            "nuclear",
            "khamenei",
            "persian gulf",
            "iranian",
            "houthi",
            "hezbollah",
            "idf",
            "yemen",
            "lebanon",
        ]
        # Basic Farsi conflict keywords for Iran context
        keywords_fa = [
            "ایران",
            "تهران",
            "سپاه پاسداران",
            "سپاه",
            "خلیج فارس",
            "خامنه‌ای",
            "حزب‌الله",
            "یمن",
            "لبنان",
            "هسته‌ای",
        ]
    elif "ukraine" in cl or "russia" in cl:
        keywords_en = ["ukraine", "russia", "kyiv", "donbas", "nato", "zelensky", "invasion"]
    else:
        keywords_en = [w for w in conflict.split() if len(w) > 2][:5] or ["conflict", "military"]
    results = []

    def _matches_keywords(title: str, summary: str) -> bool:
        lower = f"{title} {summary}".lower()
        if any(kw in lower for kw in keywords_en):
            return True
        full = f"{title} {summary}"
        if any(kw in full for kw in keywords_fa):
            return True
        return False

    for feed_url in feeds:
        try:
            parsed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": USER_AGENT},
            )
            for entry in getattr(parsed, "entries", [])[:15]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link") or ""
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                if not link:
                    continue
                if not _matches_keywords(title, summary):
                    continue
                score = _sentiment_keyword(f"{title} {summary}")
                source = (parsed.feed.get("title") or feed_url) if getattr(parsed, "feed", None) else feed_url
                results.append(
                    {
                        "title": title[:500],
                        "source": source,
                        "url": link,
                        "published_at": entry.get("published") or entry.get("updated"),
                        "sentiment_score": score,
                        "sentiment_label": _label(score),
                        "language": "",  # language not reliably available from RSS; leave empty
                        "source_type": "rss",
                    }
                )
        except Exception:
            continue
    return results


# ── Rule-based NEWS multi-agent building blocks ─────────────────────────────


def _run_newsapi_source_agent(conflict: str, hours_back: int = 48) -> Dict[str, Any]:
    """Source agent: NewsAPI-only view of the conflict."""
    raw = search_conflict_news(conflict=conflict, hours_back=hours_back)
    articles = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
    return {
        "source": "newsapi",
        "articles": articles,
        "count": len(articles),
    }


def _run_gdelt_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: GDELT-only view of the conflict."""
    raw = search_gdelt_news(conflict=conflict)
    articles = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
    return {
        "source": "gdelt",
        "articles": articles,
        "count": len(articles),
    }


def _run_rss_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: curated RSS/think-tank/OSINT feeds."""
    feeds = _rss_feeds_for_conflict(conflict)

    def _parse_single_feed(feed_url: str) -> List[Dict[str, Any]]:
        try:
            parsed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": USER_AGENT},
            )
            cl = conflict.lower()
            keywords_en: List[str]
            keywords_fa: List[str]
            if "iran" in cl:
                keywords_en = [
                    "iran",
                    "irgc",
                    "tehran",
                    "nuclear",
                    "khamenei",
                    "persian gulf",
                    "iranian",
                    "houthi",
                    "hezbollah",
                    "idf",
                    "yemen",
                    "lebanon",
                ]
                keywords_fa = [
                    "ایران",
                    "تهران",
                    "سپاه پاسداران",
                    "سپاه",
                    "خلیج فارس",
                    "خامنه‌ای",
                    "حزب‌الله",
                    "یمن",
                    "لبنان",
                    "هسته‌ای",
                ]
            elif "ukraine" in cl or "russia" in cl:
                keywords_en = ["ukraine", "russia", "kyiv", "donbas", "nato", "zelensky", "invasion"]
                keywords_fa = []
            else:
                keywords_en = [w for w in conflict.split() if len(w) > 2][:5] or ["conflict", "military"]
                keywords_fa = []

            def _matches(title: str, summary: str) -> bool:
                lower = f"{title} {summary}".lower()
                if any(kw in lower for kw in keywords_en):
                    return True
                full = f"{title} {summary}"
                if any(kw in full for kw in keywords_fa):
                    return True
                return False

            out: List[Dict[str, Any]] = []
            for entry in getattr(parsed, "entries", [])[:15]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link") or ""
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                if not link:
                    continue
                if not _matches(title, summary):
                    continue
                score = _sentiment_keyword(f"{title} {summary}")
                source = (parsed.feed.get("title") or feed_url) if getattr(parsed, "feed", None) else feed_url
                out.append(
                    {
                        "title": title[:500],
                        "source": source,
                        "url": link,
                        "published_at": entry.get("published") or entry.get("updated"),
                        "sentiment_score": score,
                        "sentiment_label": _label(score),
                        "language": "",
                        "source_type": "rss",
                    }
                )
            return out
        except Exception as e:
            logger.debug("NEWS: RSS feed %s failed: %s", feed_url, e)
            return []

    articles: List[Dict[str, Any]] = []
    # Run RSS fetches in parallel so feedparser parsing does not block sequentially
    with ThreadPoolExecutor(max_workers=min(8, len(feeds) or 1)) as executor:
        futures = [executor.submit(_parse_single_feed, url) for url in feeds]
        for fut in futures:
            try:
                batch = fut.result(timeout=20)
                if batch:
                    articles.extend(batch)
            except Exception as e:
                logger.debug("NEWS: RSS worker failed: %s", e)

    # Foreign Policy's curated Iran/Israel conflict project – treat as an additional curated source
    if "iran" in conflict.lower():
        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(
                    FOREIGN_POLICY_IRAN_PROJECT_URL,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                html = resp.text

            # Simple extraction of article links and titles
            pattern = re.compile(
                r'<a[^>]+href="(?P<href>https?://foreignpolicy\\.com[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
                re.IGNORECASE,
            )
            seen_urls = {a.get("url") for a in articles if a.get("url")}
            for match in pattern.finditer(html):
                url = match.group("href")
                title = (match.group("title") or "").strip()
                if not url or not title:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                score = _sentiment_keyword(title)
                articles.append(
                    {
                        "title": title[:500],
                        "source": "Foreign Policy – Iran/Israel project",
                        "url": url,
                        "published_at": "",
                        "sentiment_score": score,
                        "sentiment_label": _label(score),
                        "language": "en",
                        "source_type": "rss",
                    }
                )
        except Exception as e:
            logger.debug(
                "NEWS: Foreign Policy Iran project fetch failed for conflict '%s': %s",
                conflict,
                e,
            )

    return {
        "source": "rss",
        "articles": articles,
        "count": len(articles),
    }


def _run_newsdata_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: NewsData.io latest (200 credits/day, 10 articles/request). Only runs when NEWSDATA_API_KEY is set."""
    raw = search_newsdata_news(conflict=conflict)
    articles = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
    return {
        "source": "newsdata",
        "articles": articles,
        "count": len(articles),
    }


def _run_gnews_source_agent(conflict: str) -> Dict[str, Any]:
    """Source agent: GNews (gnews.io). Only runs when GNEWS_API_KEY is set. 100 requests/day limit."""
    raw = search_gnews_news(conflict=conflict)
    articles = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
    return {
        "source": "gnews",
        "articles": articles,
        "count": len(articles),
    }


def _run_news_fusion_agent(
    newsapi_res: Dict[str, Any],
    gdelt_res: Dict[str, Any],
    rss_res: Dict[str, Any],
    conflict: str = "",
    newsdata_res: Optional[Dict[str, Any]] = None,
    gnews_res: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fusion agent: dedupe + global sentiment/score across all sources."""
    newsdata_list = (newsdata_res or {}).get("articles", [])
    gnews_list = (gnews_res or {}).get("articles", [])
    merged = _merge_news_results(
        newsapi_list=newsapi_res.get("articles", []),
        gdelt_list=gdelt_res.get("articles", []),
        rss_list=rss_res.get("articles", []),
        conflict=conflict,
        newsdata_list=newsdata_list,
        gnews_list=gnews_list,
    )
    articles = merged.get("articles", [])
    overall = merged.get("overall_sentiment", 0.0)
    label = merged.get("sentiment_label", "NEUTRAL")
    breakdown = merged.get("source_breakdown", {"newsapi": 0, "gdelt": 0, "rss": 0, "newsdata": 0, "gnews": 0})

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

    top_sources = list(dict.fromkeys(a.get("source") or "" for a in articles[:10] if a.get("source")))

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


# ── NER enrichment (Phase 2) ─────────────────────────────────────────────────


def _run_ner_enrichment(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Run NER on deduplicated/ranked articles. Uses Haiku NER first (up to limit),
    then HF bulk NER for overflow. On Haiku error: entire batch falls back to HF.
    Returns a flat list of unique entities across all articles.
    """
    if not articles:
        return []
    texts = [((a.get("title") or "") + " " + (a.get("summary") or "")).strip()[:1000] for a in articles]
    all_entities: List[Dict[str, Any]] = []
    try:
        from services.haiku_service import HAIKU_MAX_NER_PER_RUN, batch_ner, is_haiku_failed
        from services.hf_service import ner_bulk

        haiku_texts = texts[:HAIKU_MAX_NER_PER_RUN]
        overflow_texts = texts[HAIKU_MAX_NER_PER_RUN:]

        haiku_results = run_async(batch_ner(haiku_texts))

        if is_haiku_failed() or all(r is None for r in haiku_results):
            logger.info("NEWS NER: Haiku failed, falling back to HF bulk for all %d texts", len(texts))
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
        logger.debug("NEWS NER enrichment unavailable: %s", e)

    # Deduplicate entities by (entity, type) pair
    seen = set()
    unique: List[Dict[str, Any]] = []
    for ent in all_entities:
        key = (ent.get("entity", "").lower(), ent.get("type", ""))
        if key not in seen and key[0]:
            seen.add(key)
            unique.append(ent)
    return unique


# ── Manager: fusion + escalation + NER → full domain result ─────────────────


def _news_manager(
    conflict: str,
    analyst_results: Dict[str, Any],
    context: Optional["AgentContext"] = None,
) -> Dict[str, Any]:
    """Middle management: take analyst results, run fusion + escalation + NER, return full NEWS result."""
    fetched_at = utc_now_iso()
    newsapi_res = analyst_results.get("newsapi") or {}
    rss_res = analyst_results.get("rss") or {}
    newsdata_res = analyst_results.get("newsdata") or {}
    gnews_res = analyst_results.get("gnews") or {}
    gdelt_res = {"source": "gdelt", "articles": [], "count": 0}
    if newsapi_res.get("error"):
        newsapi_res = {"source": "newsapi", "articles": [], "count": 0}
    if rss_res.get("error"):
        rss_res = {"source": "rss", "articles": [], "count": 0}
    if newsdata_res.get("error"):
        newsdata_res = {"source": "newsdata", "articles": [], "count": 0}
    if gnews_res.get("error"):
        gnews_res = {"source": "gnews", "articles": [], "count": 0}

    fusion = _run_news_fusion_agent(
        newsapi_res,
        gdelt_res,
        rss_res,
        conflict=conflict,
        newsdata_res=newsdata_res or None,
        gnews_res=gnews_res or None,
    )
    articles = fusion.get("articles", [])
    escalation_meta = _run_escalation_headline_agent(articles)
    all_entities = _run_ner_enrichment(articles)
    news_score = fusion.get("news_score", 50.0)
    esc_score = escalation_meta.get("escalation_score", 0.0)
    adjusted_news_score = max(0.0, min(100.0, news_score + esc_score * 10.0))

    n_newsapi = len(newsapi_res.get("articles") or [])
    n_rss = len(rss_res.get("articles") or [])
    n_newsdata = len(newsdata_res.get("articles") or [])
    n_gnews = len(gnews_res.get("articles") or [])
    source_results = [
        SourceResult(
            name="NewsAPI", status="ok" if n_newsapi else "error", fetched_at=fetched_at, record_count=n_newsapi
        ),
        SourceResult(name="RSS", status="ok" if n_rss else "error", fetched_at=fetched_at, record_count=n_rss),
    ]
    if "newsdata" in analyst_results:
        source_results.append(
            SourceResult(
                name="NewsData", status="ok" if n_newsdata else "error", fetched_at=fetched_at, record_count=n_newsdata
            )
        )
    if "gnews" in analyst_results:
        source_results.append(
            SourceResult(name="GNews", status="ok" if n_gnews else "error", fetched_at=fetched_at, record_count=n_gnews)
        )

    reg = get_health_registry()
    if reg:
        for sr in source_results:
            reg.record_result(sr.name, "news", sr)
    confidence = compute_confidence_from_sources(source_results)
    ok_count = sum(1 for s in source_results if s.status == "ok")
    data_freshness = "live" if ok_count >= 2 else "recent" if ok_count >= 1 else "stale" if articles else "unavailable"
    error_summary = None
    sources_missing = [s.name for s in source_results if s.status == "error"]
    if sources_missing:
        error_summary = f"{len(sources_missing)} source(s) failed: {', '.join(sources_missing)}"
    meta = AgentMetadata(
        agent="news",
        fetched_at=fetched_at,
        duration_ms=0,
        sources=source_results,
        confidence=confidence,
        data_freshness=data_freshness,
        fallback_used=False,
        error_summary=error_summary,
    )
    bd = fusion.get("source_breakdown", {"newsapi": 0, "gdelt": 0, "rss": 0, "newsdata": 0, "gnews": 0})
    handoff_note = ""
    if context and getattr(context, "peer_summaries", None) and getattr(context, "peer_summaries", {}):
        handoff_note = " Handoff: cross-referenced with peer agent summaries."
    summary_parts = [f"{bd.get('newsapi', 0)} NewsAPI", f"{bd.get('rss', 0)} RSS"]
    if "newsdata" in analyst_results:
        summary_parts.append(f"{bd.get('newsdata', 0)} NewsData")
    if "gnews" in analyst_results:
        summary_parts.append(f"{bd.get('gnews', 0)} GNews")
    return {
        "conflict": conflict,
        "articles": articles,
        "overall_sentiment": fusion.get("overall_sentiment", 0.0),
        "sentiment_label": fusion.get("sentiment_label", "NEUTRAL"),
        "top_sources": fusion.get("top_sources", []),
        "news_score": adjusted_news_score,
        "summary": "News (rule-based multi-agent): "
        + ", ".join(summary_parts)
        + f".{handoff_note} Sentiment: {fusion.get('sentiment_label', 'NEUTRAL')}. Escalation score: {esc_score:.2f}.",
        "source_breakdown": bd,
        "escalation_headlines": escalation_meta.get("escalation_headlines", []),
        "escalation_score": esc_score,
        "entities": all_entities,
        "_meta": meta.model_dump(mode="json"),
    }


# ── Rule-based: Analysts → Manager (domain_runner) ────────────────────────────


def _run_rule_based_news(conflict: str, context: Optional["AgentContext"] = None) -> Dict[str, Any]:
    """Execute NEWS as multi-agent: analysts in parallel, then manager (fusion + escalation + NER)."""
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    analysts: List[tuple] = [
        ("newsapi", _run_newsapi_source_agent),
        ("rss", _run_rss_source_agent),
    ]
    if os.getenv("NEWSDATA_API_KEY"):
        analysts.append(("newsdata", _run_newsdata_source_agent))
    if os.getenv("GNEWS_API_KEY"):
        analysts.append(("gnews", _run_gnews_source_agent))
    try:
        result = run_domain_with_analysts(
            conflict,
            analysts=analysts,
            manager=_news_manager,
            context=context,
            analyst_timeout_s=35.0,
            max_workers=5,
        )
        result["_meta"]["duration_ms"] = int((time.perf_counter() - start) * 1000)
        if not (result.get("articles") or []):
            logger.warning("NEWS: All %d source(s) returned 0 articles for conflict '%s'", len(analysts), conflict)
        return result
    except Exception as e:
        logger.exception("NEWS: domain pipeline failed for conflict '%s': %s", conflict, e)
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(
            agent="news",
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            sources=[],
            confidence=compute_confidence_from_sources([]),
            data_freshness="unavailable",
            fallback_used=True,
            error_summary=str(e),
        )
        return {
            "conflict": conflict,
            "articles": [],
            "overall_sentiment": 0.0,
            "sentiment_label": "NEUTRAL",
            "top_sources": [],
            "news_score": 50.0,
            "summary": "NEWS data unavailable.",
            "source_breakdown": {"newsapi": 0, "gdelt": 0, "rss": 0, "newsdata": 0, "gnews": 0},
            "_meta": meta.model_dump(mode="json"),
        }


# ── Agent ──────────────────────────────────────────────────────────────────

NEWS_SYSTEM = """You are a NEWS/OSINT analyst monitoring open-source media.
Your job: fetch news from NewsAPI and RSS, combine and analyze. (GDELT news disabled.)

You MUST call both tools: search_conflict_news, search_rss_feeds.
Then combine results as follows:
- Deduplicate by URL (keep first occurrence).
- Compute overall_sentiment as weighted average: NewsAPI weight 0.5, RSS 0.2.
- Return top 20 articles total, sorted by sentiment_score descending.
- Add source_breakdown: {"newsapi": N, "rss": N} with article counts per source.

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
  "source_breakdown": {"newsapi": N, "rss": N}
}"""


_NEWS_TOOL_FNS = {
    "search_conflict_news": search_conflict_news,
    "search_rss_feeds": search_rss_feeds,
}
_NEWS_TOOL_SCHEMAS = [
    {
        "name": "search_conflict_news",
        "description": "Search NewsAPI for conflict-related articles.",
        "input_schema": {
            "type": "object",
            "properties": {"conflict": {"type": "string"}, "hours_back": {"type": "integer"}},
            "required": ["conflict"],
        },
    },
    {
        "name": "search_rss_feeds",
        "description": "Search curated RSS/think-tank feeds.",
        "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
    },
]


def run_news_agent(conflict: str, context: Optional["AgentContext"] = None) -> Dict[str, Any]:
    def rule_based(c: str):
        return _run_rule_based_news(c, context)

    return run_agent_with_fallback(
        conflict,
        rule_based_fn=rule_based,
        system_prompt=NEWS_SYSTEM,
        user_content_template="Analyze news coverage for conflict: {conflict}",
        tool_fns=_NEWS_TOOL_FNS,
        tool_schemas=_NEWS_TOOL_SCHEMAS,
    )
