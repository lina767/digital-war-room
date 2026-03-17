"""
PROTEST / Civil Society Agent – ACLED protests & riots, GDELT protest events.

Three data sources:
1. ACLED Aggregated (real-time, weekly CSV from cookie-auth download)
2. ACLED API (event-level, ~12-month lag on Research level)
3. GDELT DOC 2.0 (real-time articles, free)

Score combines aggregated weekly event counts with GDELT article coverage.
"""
import asyncio
import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .utils import run_async
from services.acled_auth import get_acled_token_async, has_acled_oauth

logger = logging.getLogger(__name__)

ACLED_API_URL = "https://acleddata.com/api/acled/read"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
ACLED_AGGREGATED_DIR = Path(__file__).resolve().parent.parent / "data" / "acled"

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


COUNTRY_CSV_FILES = {
    "Iran": "acled_iran_aggregated_current.csv",
    "Israel": "acled_israel_aggregated_current.csv",
    "Palestine": "acled_palestine_aggregated_current.csv",
    "Yemen": "acled_yemen_aggregated_current.csv",
    "Syria": "acled_syria_aggregated_current.csv",
    "Iraq": "acled_iraq_aggregated_current.csv",
    "Lebanon": "acled_lebanon_aggregated_current.csv",
}


def _load_acled_aggregated(conflict: str) -> Dict[str, Any]:
    """Load current weekly aggregated ACLED data from downloaded CSV.
    Returns {'weeks': [...], 'latest_week': str, 'total_events': int, ...} or empty dict."""
    country = _conflict_to_country(conflict)
    csv_name = COUNTRY_CSV_FILES.get(country, f"acled_{country.lower()}_aggregated_current.csv")
    csv_path = ACLED_AGGREGATED_DIR / csv_name
    if not csv_path.exists():
        logger.info("ACLED aggregated CSV not found at %s", csv_path)
        return {}
    try:
        rows = []
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("event_type") in ("Protests", "Riots", "Violence against civilians"):
                    rows.append(row)
        if not rows:
            return {}
        from collections import defaultdict
        weekly: Dict[str, Dict[str, int]] = defaultdict(lambda: {"protests": 0, "riots": 0, "vac": 0, "fatalities": 0})
        for r in rows:
            w = r.get("week", "")
            ev = int(r.get("events") or 0)
            fat = int(r.get("fatalities") or 0)
            if r["event_type"] == "Protests":
                weekly[w]["protests"] += ev
            elif r["event_type"] == "Riots":
                weekly[w]["riots"] += ev
            else:
                weekly[w]["vac"] += ev
            weekly[w]["fatalities"] += fat

        sorted_weeks = sorted(weekly.keys())
        recent_weeks = sorted_weeks[-4:] if len(sorted_weeks) >= 4 else sorted_weeks
        recent_data = [{"week": w, **weekly[w]} for w in recent_weeks]
        latest = recent_data[-1] if recent_data else {}
        total_recent = sum(d["protests"] + d["riots"] + d["vac"] for d in recent_data)
        total_fatalities = sum(d["fatalities"] for d in recent_data)
        logger.info("ACLED aggregated: %d weeks, latest=%s, recent_4w_events=%d",
                     len(sorted_weeks), recent_weeks[-1] if recent_weeks else "?", total_recent)
        return {
            "weeks": recent_data,
            "latest_week": recent_weeks[-1] if recent_weeks else "",
            "total_events_4w": total_recent,
            "total_fatalities_4w": total_fatalities,
            "latest_protests": latest.get("protests", 0),
            "latest_riots": latest.get("riots", 0),
        }
    except Exception as e:
        logger.warning("ACLED aggregated CSV load failed: %s", e)
        return {}


async def _fetch_acled_protests(api_key: str, conflict: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch ACLED events via OAuth. Research-level: data lagged ~12 months,
    so we query 18 months to capture whatever is available."""
    country = _conflict_to_country(conflict)
    events: List[Dict[str, Any]] = []
    if not has_acled_oauth():
        logger.info("ACLED: no OAuth credentials (ACLED_EMAIL + ACLED_PASSWORD). Skipping.")
        return []
    token = await get_acled_token_async()
    if not token:
        logger.warning("ACLED: OAuth token request failed. Check ACLED_EMAIL/ACLED_PASSWORD.")
        return []
    try:
        end_d = datetime.now(timezone.utc)
        start_d = end_d - timedelta(days=540)
        event_date_val = f"{start_d.strftime('%Y-%m-%d')}|{end_d.strftime('%Y-%m-%d')}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=25.0) as client:
            for event_type in PROTEST_EVENT_TYPES[:2]:
                params = {
                    "_format": "json",
                    "limit": limit,
                    "country": country,
                    "event_type": event_type,
                    "event_date": event_date_val,
                    "event_date_where": "BETWEEN",
                }
                resp = await client.get(ACLED_API_URL, params=params, headers=headers)
                if resp.status_code != 200:
                    logger.warning("ACLED HTTP %s for %s/%s: %.200s",
                                   resp.status_code, country, event_type, resp.text)
                    continue
                data = resp.json()
                events.extend(_parse_acled_records(data))
        logger.info("ACLED: fetched %d events for %s (Protests+Riots, last 18 months)", len(events), country)
    except Exception as e:
        logger.warning("ACLED request failed: %s", e)
        return [{"error": str(e)}]
    return events[:200]


async def _fetch_gdelt_protest(conflict: str) -> List[Dict[str, Any]]:
    """Fetch GDELT DOC 2.0 API for protest-related articles (free, no key).
    Retries on 429 (rate limit) with increasing backoff."""
    query = f"{conflict} protest"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    GDELT_DOC_URL,
                    params={
                        "query": query,
                        "mode": "artlist",
                        "format": "json",
                        "maxrecords": 15,
                        "timespan": "72H",
                    },
                )
                if resp.status_code == 429:
                    if attempt < max_retries - 1:
                        wait = 8 * (attempt + 1)
                        logger.info("GDELT protest: 429 rate-limited, waiting %ds (attempt %d)", wait, attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("GDELT protest: rate-limited after %d attempts", max_retries)
                    return [{"error": "GDELT rate-limited (429)"}]
                if resp.status_code != 200:
                    logger.warning("GDELT protest: HTTP %s: %.200s", resp.status_code, resp.text)
                    return [{"error": f"GDELT HTTP {resp.status_code}"}]
                ct = (resp.headers.get("content-type") or "").lower()
                if "json" not in ct and "javascript" not in ct:
                    if attempt < max_retries - 1:
                        logger.info("GDELT protest: non-JSON response, retrying")
                        await asyncio.sleep(8)
                        continue
                    return [{"error": f"GDELT returned non-JSON (CT: {ct})"}]
                data = resp.json()
            articles: list = []
            if isinstance(data, dict):
                for key in ("articles", "articleList", "results", "docs", "ArticleList"):
                    val = data.get(key)
                    if isinstance(val, list):
                        articles = val
                        break
            return [
                {
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "date": a.get("seendate"),
                    "source": a.get("domain") or (a.get("source", {}).get("name") if isinstance(a.get("source"), dict) else None),
                }
                for a in articles[:15]
                if isinstance(a, dict) and a.get("url")
            ]
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(8)
                continue
            logger.warning("GDELT protest: exception after %d attempts: %s", max_retries, e)
            return [{"error": str(e)}]
    return []


def _compute_protest_score(
    acled_events: List[Dict],
    gdelt_articles: List[Dict],
    aggregated: Optional[Dict] = None,
) -> float:
    """Score 0-100 combining aggregated weekly counts, historical events, and GDELT coverage."""
    base = 20.0

    agg = aggregated or {}
    recent_events = agg.get("total_events_4w", 0)
    recent_fatalities = agg.get("total_fatalities_4w", 0)
    if recent_events >= 200:
        base += 30
    elif recent_events >= 100:
        base += 22
    elif recent_events >= 30:
        base += 15
    elif recent_events >= 5:
        base += 8
    if recent_fatalities > 50:
        base += 15
    elif recent_fatalities > 10:
        base += 8

    valid_acled = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if len(valid_acled) >= 30:
        base += 10
    elif len(valid_acled) >= 5:
        base += 5

    valid_gdelt = [a for a in gdelt_articles if isinstance(a, dict) and a.get("title") and "error" not in a]
    if len(valid_gdelt) >= 5:
        base += 15
    elif len(valid_gdelt) >= 1:
        base += 5
    return min(100.0, max(0.0, base))


def _build_summary(
    acled_events: List[Dict],
    gdelt_articles: List[Dict],
    score: float,
    aggregated: Optional[Dict] = None,
) -> str:
    parts = []
    agg = aggregated or {}
    if agg.get("weeks"):
        latest = agg["weeks"][-1]
        parts.append(
            f"ACLED aggregated (week {agg.get('latest_week', '?')}): "
            f"{latest.get('protests', 0)} protests, {latest.get('riots', 0)} riots, "
            f"{latest.get('fatalities', 0)} fatalities. "
            f"Last 4 weeks: {agg.get('total_events_4w', 0)} events total."
        )
    valid_a = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if valid_a:
        dates = [e.get("date") for e in valid_a if e.get("date")]
        date_range = f" ({min(dates)}–{max(dates)})" if dates else ""
        parts.append(f"ACLED historical: {len(valid_a)} events{date_range}.")
    valid_g = [a for a in gdelt_articles if a.get("title") and "error" not in a]
    if valid_g:
        parts.append(f"GDELT: {len(valid_g)} protest articles (72h).")
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

    async def _run() -> Dict[str, Any]:
        try:
            from services.acled_aggregated import refresh_acled_aggregated
            refresh_acled_aggregated()
        except Exception as e:
            logger.debug("ACLED aggregated refresh skipped: %s", e)
        aggregated = _load_acled_aggregated(conflict)
        acled_events = await _fetch_acled_protests("", conflict)
        gdelt_articles = await _fetch_gdelt_protest(conflict)
        protest_score = _compute_protest_score(acled_events, gdelt_articles, aggregated)
        base_summary = _build_summary(acled_events, gdelt_articles, protest_score, aggregated)
        cluster_summary = await _cluster_protest_events_haiku(acled_events)
        if cluster_summary:
            summary = f"{base_summary} Clusters: {cluster_summary}"
        else:
            summary = base_summary
        return {
            "protest_score": round(protest_score, 1),
            "protest_events": acled_events,
            "protest_articles": gdelt_articles,
            "acled_aggregated": aggregated,
            "summary": summary,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        events = out.get("protest_events") or []
        articles = out.get("protest_articles") or []
        agg = out.get("acled_aggregated") or {}
        acled_ok = bool(events and not (isinstance(events, list) and events and isinstance(events[0], dict) and events[0].get("error")))
        gdelt_ok = bool(articles and not (isinstance(articles, list) and articles and isinstance(articles[0], dict) and articles[0].get("error")))
        agg_ok = bool(agg.get("weeks"))
        source_results = [
            SourceResult(name="ACLED-Aggregated", status="ok" if agg_ok else "error", fetched_at=fetched_at, record_count=agg.get("total_events_4w", 0)),
            SourceResult(name="ACLED-API", status="ok" if acled_ok else "error", fetched_at=fetched_at, record_count=len(events)),
            SourceResult(name="GDELT", status="ok" if gdelt_ok else "error", fetched_at=fetched_at, record_count=len(articles)),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "protest", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count >= 2 else "recent" if ok_count == 1 else "stale" if (events or articles or agg_ok) else "unavailable"
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
