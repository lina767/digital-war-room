import asyncio
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import httpx


NEWS_API_URL = "https://newsapi.org/v2/everything"

# Trusted domains for conflict/geopolitical coverage
NEWS_DOMAINS = (
    "reuters.com,apnews.com,bbc.com,aljazeera.com,theguardian.com,"
    "nytimes.com,washingtonpost.com,ft.com,bloomberg.com,politico.com,"
    "foreignpolicy.com,defensenews.com,jpost.com,haaretz.com,irna.ir,"
    "middleeasteye.net,thehill.com"
)

# Title substrings that indicate off-topic articles (case-insensitive)
TITLE_EXCLUDE_KEYWORDS = [
    "marathon",
    "eurovision",
    "recruitment",
    "education",
    "cricket",
    "bollywood",
    "sports",
    "weather",
]

ESCALATION_KEYWORDS = [
    "attack",
    "strike",
    "missile",
    "war",
    "explosion",
    "killed",
    "military",
    "troops",
    "nuclear",
    "threat",
    "sanctions",
    "retaliation",
]

DE_ESCALATION_KEYWORDS = [
    "ceasefire",
    "talks",
    "diplomatic",
    "deal",
    "agreement",
    "withdraw",
    "peace",
    "negotiate",
    "relief",
]


def _build_query(conflict: str) -> str:
    """Build a conflict-specific NewsAPI query for highly relevant articles."""
    conflict_lower = conflict.strip().lower()

    if "iran" in conflict_lower:
        return (
            '(Iran OR IRGC OR "Persian Gulf" OR "Strait of Hormuz" '
            'OR Khamenei OR Rouhani OR "nuclear deal" OR "Iranian military") '
            "AND (US OR America OR strike OR sanctions OR military OR nuclear)"
        )

    if "ukraine" in conflict_lower:
        return (
            '(Ukraine OR Zelensky OR Kyiv OR Donbas OR "Donbass" OR Crimea) '
            "AND (Russia OR invasion OR NATO OR military OR sanctions OR war)"
        )

    # Default: use conflict string directly (quote if it contains spaces)
    conflict_term = conflict.strip()
    if not conflict_term:
        return "conflict OR military OR war"
    if " " in conflict_term:
        return f'"{conflict_term}"'
    return conflict_term


def _safe_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # NewsAPI returns ISO8601 with Z suffix; normalize for fromisoformat
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _analyze_article_sentiment(text: str) -> float:
    """
    Return sentiment score in [-1.0, 1.0] based on keyword counts.
    Positive => escalatory, negative => de-escalatory.
    """
    if not text:
        return 0.0

    lower = text.lower()
    score = 0

    for kw in ESCALATION_KEYWORDS:
        if kw in lower:
            score += 1

    for kw in DE_ESCALATION_KEYWORDS:
        if kw in lower:
       	    score -= 1

    # Normalize to [-1, 1] with a simple clamp
    if score == 0:
        return 0.0
    # Cap raw score magnitude at 3 for normalization
    capped = max(-3, min(3, score))
    return capped / 3.0


def _label_sentiment(score: float) -> str:
    if score > 0.2:
        return "ESCALATORY"
    if score < -0.2:
        return "DE-ESCALATORY"
    return "NEUTRAL"


def _title_should_exclude(title: str) -> bool:
    """Return True if the article title indicates off-topic content."""
    if not title:
        return False
    lower = title.lower()
    return any(kw in lower for kw in TITLE_EXCLUDE_KEYWORDS)


async def _fetch_news(client: httpx.AsyncClient, conflict: str) -> Dict[str, Any]:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        raise RuntimeError("NEWS_API_KEY is not set")

    from_date = datetime.now(timezone.utc) - timedelta(hours=48)
    from_str = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "q": _build_query(conflict),
        "language": "en",
        "sortBy": "relevance",
        "pageSize": 20,
        "from": from_str,
        "domains": NEWS_DOMAINS,
        "apiKey": api_key,
    }

    resp = await client.get(NEWS_API_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def _process_articles(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float, List[str], int]:
    raw_articles = payload.get("articles") or []
    processed: List[Dict[str, Any]] = []

    scores: List[float] = []
    source_counter: Counter[str] = Counter()
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    recent_count_24h = 0

    for art in raw_articles:
        title = art.get("title") or ""
        if _title_should_exclude(title):
            continue
        description = art.get("description") or ""
        combined_text = f"{title}\n{description}"

        sentiment_score = _analyze_article_sentiment(combined_text)
        sentiment_label = _label_sentiment(sentiment_score)

        source_name = (art.get("source") or {}).get("name") or ""
        published_at_raw = art.get("publishedAt")
        published_at_dt = _safe_datetime(published_at_raw)

        if published_at_dt and published_at_dt.tzinfo is None:
            published_at_dt = published_at_dt.replace(tzinfo=timezone.utc)

        if published_at_dt and published_at_dt >= cutoff_24h:
            recent_count_24h += 1

        scores.append(sentiment_score)
        if source_name:
            source_counter[source_name] += 1

        processed.append(
            {
                "title": title,
                "source": source_name,
                "url": art.get("url"),
                "published_at": published_at_raw,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
            }
        )

    overall_sentiment = sum(scores) / len(scores) if scores else 0.0
    top_sources = [name for name, _ in source_counter.most_common(5)]

    return processed, overall_sentiment, top_sources, recent_count_24h


def _compute_news_score(overall_sentiment: float, recent_count_24h: int) -> float:
    score = 50.0

    if overall_sentiment > 0.5:
        score += 20.0
    elif 0.2 <= overall_sentiment <= 0.5:
        score += 10.0
    elif overall_sentiment < -0.2:
        score -= 15.0

    if recent_count_24h > 10:
        score += 10.0

    return max(0.0, min(100.0, score))


async def _run_news_agent_async(conflict: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        payload = await _fetch_news(client, conflict)

    articles, overall_sentiment, top_sources, recent_count_24h = _process_articles(payload)
    sentiment_label = _label_sentiment(overall_sentiment)
    news_score = _compute_news_score(overall_sentiment, recent_count_24h)

    summary = (
        f"{len(articles)} articles analyzed. "
        f"Sentiment: {sentiment_label}."
    )

    return {
        "conflict": conflict,
        "articles": articles,
        "overall_sentiment": overall_sentiment,
        "sentiment_label": sentiment_label,
        "top_sources": top_sources,
        "news_score": news_score,
        "summary": summary,
    }


def run_news_agent(conflict: str) -> Dict[str, Any]:
    """
    Public sync entrypoint for the NEWS agent.

    Uses async httpx under the hood but exposes a synchronous API
    for consistency with other agents.
    """
    return asyncio.run(_run_news_agent_async(conflict))

