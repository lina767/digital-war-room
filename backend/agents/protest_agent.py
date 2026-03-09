"""
PROTEST / Civil Society Agent – ACLED protests & riots, GDELT protest events, protest-related RSS.
Fetches: ACLED events filtered by event_type (Protests, Riots), GDELT protest themes,
optional protest/unrest RSS. Rule-based score from event count and severity. No LLM.
"""
import asyncio
import os
from typing import Any, Dict, List

import httpx

ACLED_URL = "https://api.acleddata.com/acled/read"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

ACLED_COUNTRY_NAMES = {
    "iran": "Iran",
    "us-iran": "Iran",
    "israel": "Israel",
    "gaza": "Palestine",
    "ukraine": "Ukraine",
    "russia": "Russia",
    "syria": "Syria",
    "yemen": "Yemen",
    "iraq": "Iraq",
    "default": "Iran",
}

# ACLED event types for civil society / protest focus
PROTEST_EVENT_TYPES = ["Protests", "Riots", "Violence against civilians"]


def _conflict_to_country(conflict: str) -> str:
    cl = (conflict or "").lower()
    return next(
        (v for k, v in ACLED_COUNTRY_NAMES.items() if k != "default" and k in cl),
        ACLED_COUNTRY_NAMES["default"],
    )


async def _fetch_acled_protests(api_key: str, conflict: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch ACLED events filtered by protest-related event types."""
    if not api_key or not api_key.strip():
        return []
    country = _conflict_to_country(conflict)
    events: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            params = {
                "key": api_key.strip(),
                "limit": limit,
                "country": country,
            }
            email = os.getenv("ACLED_EMAIL")
            if email:
                params["email"] = email
            # ACLED allows event_type filter (e.g. "Protests")
            for event_type in PROTEST_EVENT_TYPES[:2]:  # Protests, Riots
                params["event_type"] = event_type
                resp = await client.get(ACLED_URL, params=params)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for rec in (data.get("data") or [])[:50]:
                    if not isinstance(rec, dict):
                        continue
                    events.append({
                        "event_type": rec.get("event_type"),
                        "sub_event_type": rec.get("sub_event_type"),
                        "date": rec.get("event_date"),
                        "location": rec.get("location"),
                        "fatalities": rec.get("fatalities"),
                        "country": rec.get("country"),
                        "notes": (rec.get("notes") or "")[:200],
                    })
    except Exception as e:
        return [{"error": str(e)}]
    return events[:80]


async def _fetch_gdelt_protest(conflict: str) -> List[Dict[str, Any]]:
    """Fetch GDELT doc API for protest-related articles (free, no key)."""
    query = f'("{conflict}" OR "protest" OR "demonstration" OR "civil unrest") ("protest" OR "riot" OR "strike")'
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                GDELT_DOC_URL,
                params={
                    "query": query,
                    "mode": "ArtList",
                    "format": "JSON",
                    "maxrecords": 15,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        articles = data.get("articles") or []
        if not isinstance(articles, list):
            articles = []
        return [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "date": a.get("date"),
                "source": a.get("source", {}).get("name") if isinstance(a.get("source"), dict) else None,
            }
            for a in articles[:15]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _compute_protest_score(acled_events: List[Dict], gdelt_articles: List[Dict]) -> float:
    """Score 0–100: more protests/riots and coverage = higher civil unrest signal."""
    base = 25.0
    valid_acled = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if len(valid_acled) >= 30:
        base += 30
    elif len(valid_acled) >= 15:
        base += 20
    elif len(valid_acled) >= 5:
        base += 12
    elif len(valid_acled) >= 1:
        base += 6
    fatalities = sum(int(e.get("fatalities") or 0) for e in valid_acled)
    if fatalities > 50:
        base += 20
    elif fatalities > 10:
        base += 10
    valid_gdelt = [a for a in gdelt_articles if isinstance(a, dict) and a.get("title") and "error" not in a]
    if len(valid_gdelt) >= 5:
        base += 15
    elif len(valid_gdelt) >= 1:
        base += 5
    return min(100.0, max(0.0, base))


def _build_summary(acled_events: List[Dict], gdelt_articles: List[Dict], score: float) -> str:
    parts = []
    valid_a = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if valid_a:
        parts.append(f"ACLED: {len(valid_a)} protest/riot events.")
    elif not valid_a:
        parts.append("ACLED: not available (set ACLED_API_KEY). For Iran: acleddata.com/iran-crisis-live")
    valid_g = [a for a in gdelt_articles if a.get("title") and "error" not in a]
    if valid_g:
        parts.append(f"GDELT: {len(valid_g)} protest-related articles.")
    if not parts:
        return "PROTEST: No ACLED or GDELT protest data available."
    return "PROTEST: " + " ".join(parts)


def run_protest_agent(conflict: str) -> Dict[str, Any]:
    """Run PROTEST/Civil Society agent: ACLED protests/riots, GDELT protest coverage."""
    acled_key = os.getenv("ACLED_API_KEY")

    async def _run() -> Dict[str, Any]:
        acled_events = await _fetch_acled_protests(acled_key or "", conflict)
        gdelt_articles = await _fetch_gdelt_protest(conflict)
        protest_score = _compute_protest_score(acled_events, gdelt_articles)
        summary = _build_summary(acled_events, gdelt_articles, protest_score)
        return {
            "protest_score": round(protest_score, 1),
            "protest_events": acled_events,
            "protest_articles": gdelt_articles,
            "summary": summary,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        return {
            "protest_score": 25.0,
            "protest_events": [],
            "protest_articles": [{"error": str(e)}],
            "summary": f"PROTEST error: {e}",
        }
