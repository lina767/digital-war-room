"""
PROTEST / Civil Society Agent – ACLED protests & riots, GDELT protest events, protest-related RSS.
Fetches: ACLED events filtered by event_type (Protests, Riots), GDELT protest themes,
optional protest/unrest RSS. Rule-based score from event count and severity. No LLM.
ACLED: OAuth (ACLED_EMAIL + ACLED_PASSWORD) at acleddata.com/api; see acleddata.com/api-documentation/getting-started.
"""
import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from .utils import run_async
from services.acled_auth import get_acled_token_async, has_acled_oauth

# ACLED API: OAuth uses acleddata.com; legacy key used api.acleddata.com
ACLED_API_URL = "https://acleddata.com/api/acled/read"
ACLED_LEGACY_URL = "https://api.acleddata.com/acled/read"
# GDELT DOC 2.0 API; data overview: https://www.gdeltproject.org/data.html
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
    "lebanon": "Lebanon",
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


def _parse_acled_records(data: Any) -> List[Dict[str, Any]]:
    """Parse ACLED API response (data array) into list of event dicts."""
    events: List[Dict[str, Any]] = []
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
    return events


async def _fetch_acled_protests(api_key: str, conflict: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch ACLED events filtered by protest-related event types. Uses OAuth (ACLED_EMAIL+PASSWORD) or legacy key."""
    country = _conflict_to_country(conflict)
    events: List[Dict[str, Any]] = []
    use_oauth = has_acled_oauth()
    token = await get_acled_token_async() if use_oauth else None
    if use_oauth and not token:
        return []
    if not use_oauth and (not api_key or not api_key.strip()):
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for event_type in PROTEST_EVENT_TYPES[:2]:  # Protests, Riots
                params = {"_format": "json", "limit": limit, "country": country, "event_type": event_type}
                if use_oauth and token:
                    resp = await client.get(
                        ACLED_API_URL,
                        params=params,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                else:
                    params["key"] = api_key.strip()
                    if os.getenv("ACLED_EMAIL"):
                        params["email"] = os.getenv("ACLED_EMAIL", "")
                    resp = await client.get(ACLED_LEGACY_URL, params=params)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                events.extend(_parse_acled_records(data))
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
        parts.append("ACLED: not available (set ACLED_EMAIL + ACLED_PASSWORD for OAuth). For Iran: acleddata.com/iran-crisis-live")
    valid_g = [a for a in gdelt_articles if a.get("title") and "error" not in a]
    if valid_g:
        parts.append(f"GDELT: {len(valid_g)} protest-related articles.")
    if not parts:
        return "PROTEST: No ACLED or GDELT protest data available."
    return "PROTEST: " + " ".join(parts)


async def _cluster_protest_events_haiku(acled_events: List[Dict]) -> Optional[str]:
    """Use Haiku to summarize ACLED events as 2-4 protest clusters (location, count, grievance)."""
    valid = [e for e in acled_events if isinstance(e, dict) and "error" not in e][:20]
    if not valid:
        return None
    lines = []
    for i, e in enumerate(valid, 1):
        loc = e.get("location") or e.get("country") or "Unknown"
        etype = e.get("event_type") or e.get("sub_event_type") or "Protest"
        notes = (e.get("notes") or "").strip()[:150]
        lines.append(f"Event {i}: {loc}, {etype}, {notes}")
    text = (
        "Identify 2-4 protest clusters by geography and cause. For each cluster give: location, "
        "approximate event count, and primary grievance.\n\nProtest events:\n" + "\n".join(lines)
    )
    try:
        from services.haiku_service import summarize
        out = await summarize(text[:4000], max_output_tokens=200)
        return out.strip() if out else None
    except Exception:
        return None


def run_protest_agent(conflict: str) -> Dict[str, Any]:
    """Run PROTEST/Civil Society agent: ACLED protests/riots, GDELT protest coverage."""
    import time
    from .health_registry import get_health_registry
    from .utils import AgentMetadata, SourceResult, utc_now_iso, compute_confidence_from_sources

    acled_key = os.getenv("ACLED_API_KEY", "").strip() if not has_acled_oauth() else ""

    async def _run() -> Dict[str, Any]:
        acled_events = await _fetch_acled_protests(acled_key, conflict)
        gdelt_articles = await _fetch_gdelt_protest(conflict)
        protest_score = _compute_protest_score(acled_events, gdelt_articles)
        base_summary = _build_summary(acled_events, gdelt_articles, protest_score)
        cluster_summary = await _cluster_protest_events_haiku(acled_events)
        if cluster_summary:
            summary = f"{base_summary} Clusters: {cluster_summary}"
        else:
            summary = base_summary
        return {
            "protest_score": round(protest_score, 1),
            "protest_events": acled_events,
            "protest_articles": gdelt_articles,
            "summary": summary,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        events = out.get("protest_events") or []
        articles = out.get("protest_articles") or []
        acled_ok = bool(events and not (isinstance(events, list) and events and isinstance(events[0], dict) and events[0].get("error")))
        gdelt_ok = bool(articles and not (isinstance(articles, list) and articles and isinstance(articles[0], dict) and articles[0].get("error")))
        source_results = [
            SourceResult(name="ACLED", status="ok" if acled_ok else "error", fetched_at=fetched_at, record_count=len(events)),
            SourceResult(name="GDELT", status="ok" if gdelt_ok else "error", fetched_at=fetched_at, record_count=len(articles)),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "protest", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count == 2 else "recent" if ok_count == 1 else "stale" if (events or articles) else "unavailable"
        meta = AgentMetadata(agent="protest", fetched_at=fetched_at, duration_ms=duration_ms, sources=source_results, confidence=confidence, data_freshness=data_freshness, fallback_used=False, error_summary=None)
        out["_meta"] = meta.model_dump(mode="json")
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(agent="protest", fetched_at=fetched_at, duration_ms=duration_ms, sources=[], confidence=compute_confidence_from_sources([]), data_freshness="unavailable", fallback_used=True, error_summary=str(e))
        return {
            "protest_score": 25.0,
            "protest_events": [],
            "protest_articles": [{"error": str(e)}],
            "summary": f"PROTEST error: {e}",
            "_meta": meta.model_dump(mode="json"),
        }
