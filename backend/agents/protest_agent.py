"""
PROTEST / Civil Society Agent — civil unrest and protest signals.

Sources:
1. ACLED aggregated weekly CSV (cookie refresh) and optional legacy Read-API (PROTEST_USE_ACLED_API)
2. ACLED crisis/analysis pages scraped from region hubs (ACLED_CRISIS_HUB_URLS)
3. GDELT DOC 2.0 (protest news), GDELT Events + GKG via BigQuery when configured
4. HDX HAPI conflict-events (optional app id) and INFORM GCSI via HDX CKAN (XLSX)
"""

import asyncio
import csv
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from services.acled_crisis_scrape import fetch_acled_crisis_pages_async
from services.acled_auth import get_acled_token_async, has_acled_oauth
from services.gdelt_bigquery import fetch_gdelt_gkg_protest_context, fetch_gdelt_protest_events_summary
from services.hdx_inform import fetch_inform_for_iso3

from .contracts import get_agent_fallback
from .utils import build_agent_meta, run_async

logger = logging.getLogger(__name__)

ACLED_API_URL = "https://acleddata.com/api/acled/read"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
HAPI_BASE_URL = "https://hapi.humdata.org/api/v1"
HAPI_APP_IDENTIFIER = (os.getenv("HAPI_APP_IDENTIFIER") or "").strip()
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

HAPI_ISO3_BY_CONFLICT = {
    "iran": ["IRN"],
    "israel": ["ISR"],
    "gaza": ["PSE", "ISR"],
    "yemen": ["YEM"],
    "lebanon": ["LBN"],
    "syria": ["SYR"],
    "iraq": ["IRQ"],
    "ukraine": ["UKR"],
    "russia": ["RUS"],
    "default": ["IRN", "SYR", "YEM", "PSE", "ISR"],
}

# ACLED event types for civil society / protest focus
PROTEST_EVENT_TYPES = ["Protests", "Riots", "Violence against civilians"]

# Protest-context escalation weights (weekly aggregated view by event_type).
W_PROTEST = 1.0
W_RIOT = 1.35
W_VAC = 1.8  # Violence against civilians => clear escalation signal.

INTENSITY_KEYWORDS = [
    "tear gas",
    "curfew",
    "state of emergency",
    "mobilization",
]

ACLED_STALE_DAYS = int((os.getenv("PROTEST_ACLED_STALE_DAYS") or "120").strip())
ACLED_AGGREGATED_FRESH_DAYS = int((os.getenv("PROTEST_ACLED_FRESH_DAYS") or "14").strip())
PROTEST_ASYNC_TIMEOUT_S = float((os.getenv("PROTEST_RUN_ASYNC_TIMEOUT_S") or "300").strip())


def _use_acled_read_api() -> bool:
    return (os.getenv("PROTEST_USE_ACLED_API") or "0").strip().lower() in ("1", "true", "yes", "on")


def _gkg_bq_sync(conflict: str) -> Dict[str, Any]:
    iso3 = _iso3_from_conflict(conflict)
    country = _conflict_to_country(conflict)
    return fetch_gdelt_gkg_protest_context(conflict, iso3_list=iso3, country_names=[country])


def _conflict_to_country(conflict: str) -> str:
    cl = (conflict or "").lower()
    return next(
        (v for k, v in ACLED_COUNTRY_NAMES.items() if k != "default" and k in cl),
        ACLED_COUNTRY_NAMES["default"],
    )


def _build_gdelt_query(conflict: str) -> str:
    """Build broader GDELT query to reduce false-empty results."""
    country = _conflict_to_country(conflict)
    core_terms = '(protest OR protests OR riot OR riots OR demonstration OR strike OR unrest)'
    return f'"{country}" AND {core_terms}'


def _iso3_from_conflict(conflict: str) -> List[str]:
    cl = (conflict or "").lower()
    return next(
        (v for k, v in HAPI_ISO3_BY_CONFLICT.items() if k != "default" and k in cl),
        HAPI_ISO3_BY_CONFLICT["default"],
    )


def _result_is_error_blob(rows: List[Dict[str, Any]]) -> bool:
    return bool(rows and isinstance(rows[0], dict) and rows[0].get("error"))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _event_escalation_weight(event_type: str, sub_event_type: str) -> float:
    et = (event_type or "").strip().lower()
    st = (sub_event_type or "").strip().lower()
    if et == "violence against civilians":
        return 2.0
    if et == "riots":
        return 1.4
    if et == "protests":
        if st == "peaceful protest":
            return 0.9
        if st == "protest with intervention":
            return 1.3
        if st == "excessive force against protesters":
            return 1.8
        return 1.0
    return 1.0


def _compute_event_severity_mix(acled_events: List[Dict[str, Any]]) -> Dict[str, float]:
    """Count protest subtypes and derive an escalation index from event-level ACLED data."""
    valid = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if not valid:
        return {
            "peaceful_protest_count": 0.0,
            "protest_with_intervention_count": 0.0,
            "excessive_force_against_protesters_count": 0.0,
            "violence_against_civilians_count": 0.0,
            "escalation_index": 0.0,
        }

    peaceful = 0
    intervention = 0
    excessive_force = 0
    vac = 0
    weighted = 0.0
    for e in valid:
        et = str(e.get("event_type") or "")
        st = str(e.get("sub_event_type") or "")
        et_l = et.lower()
        st_l = st.lower()
        if et_l == "protests":
            if st_l == "peaceful protest":
                peaceful += 1
            elif st_l == "protest with intervention":
                intervention += 1
            elif st_l == "excessive force against protesters":
                excessive_force += 1
        elif et_l == "violence against civilians":
            vac += 1
        weighted += _event_escalation_weight(et, st)
    esc = weighted / max(1.0, float(len(valid)))
    return {
        "peaceful_protest_count": float(peaceful),
        "protest_with_intervention_count": float(intervention),
        "excessive_force_against_protesters_count": float(excessive_force),
        "violence_against_civilians_count": float(vac),
        "escalation_index": round(esc, 3),
    }


def _compute_gdelt_intensity_metrics(gdelt_articles: List[Dict[str, Any]]) -> Dict[str, float]:
    """Use GDELT tone and escalation keywords as instability signal."""
    valid = [a for a in gdelt_articles if isinstance(a, dict) and "error" not in a and a.get("title")]
    if not valid:
        return {
            "article_count": 0.0,
            "avg_tone": 0.0,
            "negative_tone_score": 0.0,
            "keyword_hits": 0.0,
            "keyword_hit_ratio": 0.0,
            "intensity_index": 0.0,
        }

    tones = [_safe_float(a.get("tone"), 0.0) for a in valid]
    avg_tone = sum(tones) / max(1.0, float(len(tones)))
    # More negative tone => higher score.
    negative_tone_score = max(0.0, min(10.0, -avg_tone))

    hits = 0
    for a in valid:
        title = str(a.get("title") or "").lower()
        if any(k in title for k in INTENSITY_KEYWORDS):
            hits += 1
    hit_ratio = hits / max(1.0, float(len(valid)))

    # Composite intensity: negative tone + keyword density.
    intensity_index = min(3.0, (negative_tone_score / 4.0) + (hit_ratio * 1.6))
    return {
        "article_count": float(len(valid)),
        "avg_tone": round(avg_tone, 3),
        "negative_tone_score": round(negative_tone_score, 3),
        "keyword_hits": float(hits),
        "keyword_hit_ratio": round(hit_ratio, 3),
        "intensity_index": round(intensity_index, 3),
    }


def _compute_hdx_intensity_metrics(hdx_events: List[Dict[str, Any]]) -> Dict[str, float]:
    """Summarize HDX HAPI conflict-events for protest escalation context."""
    valid = [e for e in hdx_events if isinstance(e, dict) and "error" not in e]
    if not valid:
        return {
            "event_rows": 0.0,
            "events_sum": 0.0,
            "fatalities_sum": 0.0,
            "vac_rows": 0.0,
            "protest_related_rows": 0.0,
            "intensity_index": 0.0,
        }
    events_sum = 0.0
    fatalities_sum = 0.0
    vac_rows = 0
    protest_rows = 0
    for row in valid:
        ev_type = str(row.get("event_type") or "").lower()
        events_sum += _safe_float(row.get("events"), 0.0)
        fatalities_sum += _safe_float(row.get("fatalities"), 0.0)
        if "violence against civilians" in ev_type:
            vac_rows += 1
        if any(k in ev_type for k in ("protest", "riot", "demonstration")):
            protest_rows += 1
    intensity = min(3.5, (fatalities_sum / 20.0) + (vac_rows * 0.25) + (protest_rows * 0.12))
    return {
        "event_rows": float(len(valid)),
        "events_sum": round(events_sum, 2),
        "fatalities_sum": round(fatalities_sum, 2),
        "vac_rows": float(vac_rows),
        "protest_related_rows": float(protest_rows),
        "intensity_index": round(intensity, 3),
    }


def _compute_gdelt_bq_protest_metrics(bq: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not bq or not bq.get("ok"):
        return {"total_matched": 0.0, "protest_root_share": 0.0, "intensity_index": 0.0}
    total = float(bq.get("total_matched") or 0)
    by_root = bq.get("by_event_root") or []
    pr = 0.0
    for x in by_root:
        if str(x.get("event_root_code") or "").strip() == "14":
            pr += float(x.get("count") or 0)
    share = (pr / total) if total > 0 else 0.0
    # Scale: volume + emphasis on explicit protest root share
    idx = min(3.0, (total / 1200.0) ** 0.5 + share * 2.2)
    return {
        "total_matched": total,
        "protest_root_share": round(share, 4),
        "intensity_index": round(idx, 3),
    }


def _compute_gkg_bq_metrics(gkg: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not gkg or not gkg.get("ok"):
        return {"row_count": 0.0, "theme_ratio": 0.0, "intensity_index": 0.0}
    rc = float(gkg.get("row_count") or 0)
    ratio = float(gkg.get("protest_theme_ratio") or 0)
    tone = gkg.get("avg_doc_tone")
    neg = max(0.0, -float(tone)) if tone is not None else 0.0
    idx = min(3.0, (ratio * 2.4) + min(1.5, neg / 6.0) + min(1.2, (rc / 8000.0) ** 0.5))
    return {
        "row_count": rc,
        "theme_ratio": round(ratio, 4),
        "intensity_index": round(idx, 3),
    }


def _compute_inform_risk_metrics(inform: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not inform or not inform.get("ok"):
        return {"severity": 0.0, "risk_index": 0.0}
    mx = inform.get("max_severity")
    mn = inform.get("mean_severity")
    sev = float(mx if mx is not None else mn or 0.0)
    # GCSI-style scores are model-specific; treat as 0–10 additive hints only
    idx = min(3.5, max(0.0, sev) / 3.5)
    return {"severity": round(sev, 3), "risk_index": round(idx, 3)}


def _parse_iso_date(value: Any) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_week_marker(value: Any) -> Optional[datetime]:
    """Parse ACLED aggregated latest_week markers into UTC datetime."""
    s = str(value or "").strip()
    if not s:
        return None
    dt = _parse_iso_date(s)
    if dt is not None:
        return dt
    m = re.match(r"^(\d{4})-W(\d{1,2})$", s)
    if m:
        year = int(m.group(1))
        week = int(m.group(2))
        try:
            d = datetime.fromisocalendar(year, week, 1)  # Monday
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _is_aggregated_fresh(aggregated: Optional[Dict[str, Any]], fresh_days: int = ACLED_AGGREGATED_FRESH_DAYS) -> bool:
    agg = aggregated or {}
    latest_week = agg.get("latest_week")
    dt = _parse_week_marker(latest_week)
    if dt is None:
        return False
    return dt >= (datetime.now(timezone.utc) - timedelta(days=fresh_days))


def _is_acled_stale(acled_events: List[Dict[str, Any]], stale_days: int = ACLED_STALE_DAYS) -> bool:
    valid = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if not valid:
        return True
    dates = [_parse_iso_date(e.get("date")) for e in valid]
    dates_ok = [d for d in dates if d is not None]
    if not dates_ok:
        return True
    newest = max(dates_ok)
    return newest < (datetime.now(timezone.utc) - timedelta(days=stale_days))


async def _fetch_hdx_hapi_protest(conflict: str) -> List[Dict[str, Any]]:
    """Fetch HDX HAPI conflict-events rows for conflict ISO3 countries."""
    if not HAPI_APP_IDENTIFIER:
        return []
    iso3_codes = _iso3_from_conflict(conflict)
    out: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=14.0) as client:
            for iso3 in iso3_codes[:3]:
                resp = await client.get(
                    f"{HAPI_BASE_URL}/coordination-context/conflict-events",
                    params={
                        "output_format": "json",
                        "limit": 100,
                        "app_identifier": HAPI_APP_IDENTIFIER,
                        "location_code": iso3.upper(),
                    },
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("data", data.get("results", []))
                if not isinstance(rows, list):
                    continue
                for row in rows[:25]:
                    if not isinstance(row, dict):
                        continue
                    out.append(
                        {
                            "source": "HDX HAPI",
                            "location_code": iso3.upper(),
                            "location_name": row.get("location_name"),
                            "event_type": row.get("event_type"),
                            "events": _safe_float(row.get("events"), 0.0),
                            "fatalities": _safe_float(row.get("fatalities"), 0.0),
                            "date": row.get("reference_period_end") or row.get("reference_period_start"),
                        }
                    )
    except Exception as e:
        logger.warning("HDX HAPI fetch failed: %s", e)
        return [{"error": str(e)}]
    return out[:50]


def _parse_acled_records(data: Any) -> List[Dict[str, Any]]:
    """Parse ACLED API response (data array) into list of event dicts."""
    events: List[Dict[str, Any]] = []
    for rec in (data.get("data") or [])[:50]:
        if not isinstance(rec, dict):
            continue
        events.append(
            {
                "event_type": rec.get("event_type"),
                "sub_event_type": rec.get("sub_event_type"),
                "date": rec.get("event_date"),
                "location": rec.get("location"),
                "fatalities": rec.get("fatalities"),
                "country": rec.get("country"),
                "notes": (rec.get("notes") or "")[:200],
            }
        )
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
        all_weeks = [{"week": w, **weekly[w]} for w in sorted_weeks]
        recent_weeks = sorted_weeks[-4:] if len(sorted_weeks) >= 4 else sorted_weeks
        recent_data = [{"week": w, **weekly[w]} for w in recent_weeks]
        latest = recent_data[-1] if recent_data else {}
        total_recent = sum(d["protests"] + d["riots"] + d["vac"] for d in recent_data)
        total_fatalities = sum(d["fatalities"] for d in recent_data)
        logger.info(
            "ACLED aggregated: %d weeks, latest=%s, recent_4w_events=%d",
            len(sorted_weeks),
            recent_weeks[-1] if recent_weeks else "?",
            total_recent,
        )
        return {
            "weeks": recent_data,
            "weeks_all": all_weeks,
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
            for event_type in PROTEST_EVENT_TYPES:
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
                    logger.warning("ACLED HTTP %s for %s/%s: %.200s", resp.status_code, country, event_type, resp.text)
                    continue
                data = resp.json()
                events.extend(_parse_acled_records(data))
        logger.info("ACLED: fetched %d events for %s (civil-society types, last 18 months)", len(events), country)
    except Exception as e:
        logger.warning("ACLED request failed: %s", e)
        return [{"error": str(e)}]
    return events[:200]


async def _fetch_gdelt_protest(conflict: str) -> List[Dict[str, Any]]:
    """Fetch GDELT DOC 2.0 API for protest-related articles (free, no key).
    Retries on 429 (rate limit) with increasing backoff."""
    query = _build_gdelt_query(conflict)
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
                    "tone": _safe_float(a.get("tone"), 0.0),
                    "source": a.get("domain")
                    or (a.get("source", {}).get("name") if isinstance(a.get("source"), dict) else None),
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


def _compute_dynamic_baseline_metrics(aggregated: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Compute 12-month baseline and week-over-week velocity from aggregated data."""
    agg = aggregated or {}
    weeks_all = agg.get("weeks_all") or agg.get("weeks") or []
    if not isinstance(weeks_all, list):
        weeks_all = []
    rows = [w for w in weeks_all if isinstance(w, dict)]
    if not rows:
        return {
            "latest_total": 0.0,
            "latest_fatalities": 0.0,
            "baseline_avg_12m": 0.0,
            "baseline_fatalities_12m": 0.0,
            "activity_ratio_vs_12m": 1.0,
            "velocity_wow_pct": 0.0,
            "fatality_velocity_wow_pct": 0.0,
            "weeks_in_baseline": 0.0,
        }

    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else {}

    latest_total = float(int(latest.get("protests", 0)) + int(latest.get("riots", 0)) + int(latest.get("vac", 0)))
    latest_weighted_total = float(
        int(latest.get("protests", 0)) * W_PROTEST
        + int(latest.get("riots", 0)) * W_RIOT
        + int(latest.get("vac", 0)) * W_VAC
    )
    latest_fatalities = float(int(latest.get("fatalities", 0)))
    prev_total = float(int(prev.get("protests", 0)) + int(prev.get("riots", 0)) + int(prev.get("vac", 0))) if prev else 0.0
    prev_weighted_total = (
        float(
            int(prev.get("protests", 0)) * W_PROTEST
            + int(prev.get("riots", 0)) * W_RIOT
            + int(prev.get("vac", 0)) * W_VAC
        )
        if prev
        else 0.0
    )
    prev_fatalities = float(int(prev.get("fatalities", 0))) if prev else 0.0

    baseline_rows = rows[-52:] if len(rows) > 52 else rows
    baseline_totals = [
        float(int(r.get("protests", 0)) + int(r.get("riots", 0)) + int(r.get("vac", 0)))
        for r in baseline_rows
    ]
    baseline_weighted_totals = [
        float(int(r.get("protests", 0)) * W_PROTEST + int(r.get("riots", 0)) * W_RIOT + int(r.get("vac", 0)) * W_VAC)
        for r in baseline_rows
    ]
    baseline_fatalities = [float(int(r.get("fatalities", 0))) for r in baseline_rows]
    n = max(1.0, float(len(baseline_rows)))
    baseline_avg = sum(baseline_totals) / n
    baseline_weighted_avg = sum(baseline_weighted_totals) / n
    baseline_fat_avg = sum(baseline_fatalities) / n

    if baseline_weighted_avg > 0:
        ratio = latest_weighted_total / baseline_weighted_avg
    else:
        ratio = 1.0 if latest_weighted_total <= 0 else 2.0

    if prev_weighted_total > 0:
        wow_pct = ((latest_weighted_total - prev_weighted_total) / prev_weighted_total) * 100.0
    elif latest_weighted_total > 0:
        wow_pct = 100.0
    else:
        wow_pct = 0.0

    if prev_fatalities > 0:
        fat_wow_pct = ((latest_fatalities - prev_fatalities) / prev_fatalities) * 100.0
    elif latest_fatalities > 0:
        fat_wow_pct = 100.0
    else:
        fat_wow_pct = 0.0

    return {
        "latest_total": round(latest_total, 2),
        "latest_weighted_total": round(latest_weighted_total, 2),
        "latest_fatalities": round(latest_fatalities, 2),
        "baseline_avg_12m": round(baseline_avg, 2),
        "baseline_weighted_avg_12m": round(baseline_weighted_avg, 2),
        "baseline_fatalities_12m": round(baseline_fat_avg, 2),
        "activity_ratio_vs_12m": round(ratio, 3),
        "velocity_wow_pct": round(wow_pct, 2),
        "fatality_velocity_wow_pct": round(fat_wow_pct, 2),
        "weeks_in_baseline": float(len(baseline_rows)),
    }


def _compute_protest_score(
    acled_events: List[Dict],
    gdelt_articles: List[Dict],
    hdx_events: Optional[List[Dict[str, Any]]] = None,
    aggregated: Optional[Dict] = None,
    *,
    gdelt_events_bq: Optional[Dict[str, Any]] = None,
    gdelt_gkg_bq: Optional[Dict[str, Any]] = None,
    acled_crisis_pages: Optional[List[Dict[str, Any]]] = None,
    inform_risk: Optional[Dict[str, Any]] = None,
) -> tuple[float, Dict[str, Any]]:
    """Score 0-100 using dynamic 12-month baseline and velocity signals."""
    base = 20.0
    baseline_pts = 0.0
    velocity_pts = 0.0
    fatality_velocity_pts = 0.0
    source_coverage_pts = 0.0
    severity_pts = 0.0
    gdelt_intensity_pts = 0.0
    hdx_intensity_pts = 0.0
    gdelt_bq_pts = 0.0
    gkg_pts = 0.0
    crisis_pts = 0.0
    inform_pts = 0.0

    metrics = _compute_dynamic_baseline_metrics(aggregated)
    sev = _compute_event_severity_mix(acled_events)
    gdelt_intensity = _compute_gdelt_intensity_metrics(gdelt_articles)
    hdx_intensity = _compute_hdx_intensity_metrics(hdx_events or [])
    bq_ev = _compute_gdelt_bq_protest_metrics(gdelt_events_bq)
    bq_gkg = _compute_gkg_bq_metrics(gdelt_gkg_bq)
    inform_m = _compute_inform_risk_metrics(inform_risk)
    acled_stale = _is_acled_stale(acled_events)
    aggregated_fresh = _is_aggregated_fresh(aggregated)
    is_acled_fresh = bool(aggregated_fresh and not acled_stale)

    if not is_acled_fresh:
        gdelt_weight = 0.8
        acled_weight = 0.2
    else:
        gdelt_weight = 0.4
        acled_weight = 0.6

    gdelt_primary_mode = not is_acled_fresh
    ratio = metrics.get("activity_ratio_vs_12m", 1.0)
    wow = metrics.get("velocity_wow_pct", 0.0)
    fatal_wow = metrics.get("fatality_velocity_wow_pct", 0.0)
    escalation_index = sev.get("escalation_index", 0.0)

    # Relative activity vs country-specific baseline (ACLED domain).
    if aggregated_fresh:
        if ratio >= 2.0:
            baseline_pts = 25.0
        elif ratio >= 1.5:
            baseline_pts = 18.0
        elif ratio >= 1.2:
            baseline_pts = 12.0
        elif ratio >= 1.0:
            baseline_pts = 6.0

    # Velocity: sudden acceleration is a stronger warning than static high (ACLED domain).
    if wow >= 50:
        velocity_pts = 22.0
    elif wow >= 25:
        velocity_pts = 12.0
    elif wow >= 10:
        velocity_pts = 6.0

    if fatal_wow >= 50:
        fatality_velocity_pts = 12.0
    elif fatal_wow >= 25:
        fatality_velocity_pts = 6.0

    # Event severity mix (ACLED domain).
    if escalation_index >= 1.6:
        severity_pts += 14.0
    elif escalation_index >= 1.35:
        severity_pts += 9.0
    elif escalation_index >= 1.15:
        severity_pts += 5.0

    vac_count = sev.get("violence_against_civilians_count", 0.0)
    excessive_force_count = sev.get("excessive_force_against_protesters_count", 0.0)
    if vac_count >= 5:
        severity_pts += 8.0
    elif vac_count >= 1:
        severity_pts += 4.0
    if excessive_force_count >= 5:
        severity_pts += 6.0
    elif excessive_force_count >= 1:
        severity_pts += 3.0

    # Apply domain weights.
    base += (baseline_pts + velocity_pts + fatality_velocity_pts + severity_pts) * acled_weight

    valid_acled = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if len(valid_acled) >= 30:
        source_coverage_pts += 10.0
    elif len(valid_acled) >= 5:
        source_coverage_pts += 5.0

    # GDELT: combine coverage with tone/keyword-based intensity.
    valid_gdelt = [a for a in gdelt_articles if isinstance(a, dict) and a.get("title") and "error" not in a]
    if len(valid_gdelt) >= 5:
        source_coverage_pts += 8.0
    elif len(valid_gdelt) >= 1:
        source_coverage_pts += 3.0
    if gdelt_primary_mode:
        source_coverage_pts += 8.0 if len(valid_gdelt) >= 5 else (4.0 if len(valid_gdelt) >= 1 else 0.0)
    valid_hdx = [h for h in (hdx_events or []) if isinstance(h, dict) and "error" not in h]
    if len(valid_hdx) >= 5:
        source_coverage_pts += 5.0
    elif len(valid_hdx) >= 1:
        source_coverage_pts += 2.0
    base += source_coverage_pts

    intensity_index = gdelt_intensity.get("intensity_index", 0.0)
    if intensity_index >= 2.2:
        gdelt_intensity_pts = 12.0
    elif intensity_index >= 1.5:
        gdelt_intensity_pts = 8.0
    elif intensity_index >= 0.9:
        gdelt_intensity_pts = 4.0
    if gdelt_primary_mode:
        gdelt_intensity_pts += 10.0
    base += gdelt_intensity_pts * gdelt_weight
    hdx_idx = hdx_intensity.get("intensity_index", 0.0)
    if hdx_idx >= 2.2:
        hdx_intensity_pts = 10.0
    elif hdx_idx >= 1.4:
        hdx_intensity_pts = 6.0
    elif hdx_idx >= 0.8:
        hdx_intensity_pts = 3.0
    base += hdx_intensity_pts

    # GDELT Events (BigQuery): unrest / protest-root mass in media events
    bq_idx = bq_ev.get("intensity_index", 0.0)
    if bq_idx >= 2.0:
        gdelt_bq_pts = 14.0
    elif bq_idx >= 1.3:
        gdelt_bq_pts = 9.0
    elif bq_idx >= 0.7:
        gdelt_bq_pts = 5.0
    base += gdelt_bq_pts

    gkg_idx = bq_gkg.get("intensity_index", 0.0)
    if gkg_idx >= 2.0:
        gkg_pts = 10.0
    elif gkg_idx >= 1.3:
        gkg_pts = 6.0
    elif gkg_idx >= 0.75:
        gkg_pts = 3.0
    base += gkg_pts

    crisis_valid = [
        p
        for p in (acled_crisis_pages or [])
        if isinstance(p, dict) and not p.get("error") and (p.get("excerpt") or p.get("title"))
    ]
    if len(crisis_valid) >= 6:
        crisis_pts = 10.0
    elif len(crisis_valid) >= 3:
        crisis_pts = 6.0
    elif len(crisis_valid) >= 1:
        crisis_pts = 3.0
    base += crisis_pts

    inf_idx = inform_m.get("risk_index", 0.0)
    if inf_idx >= 2.5:
        inform_pts = 6.0
    elif inf_idx >= 1.5:
        inform_pts = 4.0
    elif inf_idx >= 0.8:
        inform_pts = 2.0
    base += inform_pts

    score = min(100.0, max(0.0, base))
    breakdown: Dict[str, Any] = {
        "base": 20.0,
        "baseline": round(baseline_pts * acled_weight, 1),
        "velocity": round(velocity_pts * acled_weight, 1),
        "fatality_velocity": round(fatality_velocity_pts * acled_weight, 1),
        "source_coverage": round(source_coverage_pts, 1),
        "severity_mix": round(severity_pts * acled_weight, 1),
        "gdelt_intensity": round(gdelt_intensity_pts * gdelt_weight, 1),
        "hdx_intensity": round(hdx_intensity_pts, 1),
        "gdelt_events_bq": round(gdelt_bq_pts, 1),
        "gdelt_gkg_bq": round(gkg_pts, 1),
        "acled_crisis_pages": round(crisis_pts, 1),
        "inform_risk": round(inform_pts, 1),
        "gdelt_primary_mode": gdelt_primary_mode,
        "acled_stale": acled_stale,
        "is_acled_fresh": is_acled_fresh,
        "acled_weight": acled_weight,
        "gdelt_weight": gdelt_weight,
        "total_pre_clamp": round(base, 1),
        "total": round(score, 1),
    }
    return score, breakdown


def _build_summary(
    acled_events: List[Dict],
    gdelt_articles: List[Dict],
    hdx_events: Optional[List[Dict[str, Any]]],
    score: float,
    aggregated: Optional[Dict] = None,
    *,
    gdelt_events_bq: Optional[Dict[str, Any]] = None,
    gdelt_gkg_bq: Optional[Dict[str, Any]] = None,
    acled_crisis_pages: Optional[List[Dict[str, Any]]] = None,
    inform_risk: Optional[Dict[str, Any]] = None,
) -> str:
    parts = []
    agg = aggregated or {}
    dyn = _compute_dynamic_baseline_metrics(aggregated)
    sev = _compute_event_severity_mix(acled_events)
    gdi = _compute_gdelt_intensity_metrics(gdelt_articles)
    hdi = _compute_hdx_intensity_metrics(hdx_events or [])
    if agg.get("weeks"):
        latest = agg["weeks"][-1]
        parts.append(
            f"ACLED aggregated (week {agg.get('latest_week', '?')}): "
            f"{latest.get('protests', 0)} protests, {latest.get('riots', 0)} riots, "
            f"{latest.get('fatalities', 0)} fatalities. "
            f"Last 4 weeks: {agg.get('total_events_4w', 0)} events total."
        )
    baseline_avg = dyn.get("baseline_avg_12m", 0.0)
    velocity = dyn.get("velocity_wow_pct", 0.0)
    ratio = dyn.get("activity_ratio_vs_12m", 1.0)
    if baseline_avg > 0:
        parts.append(
            f"Baseline (12m): avg {baseline_avg:.1f} events/week; current level {ratio:.2f}x normal; WoW velocity {velocity:+.1f}%."
        )
        if velocity >= 50:
            parts.append("Acceleration alert: weekly events jumped >=50% vs previous week.")
    if sev.get("escalation_index", 0.0) > 0:
        parts.append(
            "Escalation mix: "
            f"peaceful={int(sev.get('peaceful_protest_count', 0))}, "
            f"intervention={int(sev.get('protest_with_intervention_count', 0))}, "
            f"excessive_force={int(sev.get('excessive_force_against_protesters_count', 0))}, "
            f"VAC={int(sev.get('violence_against_civilians_count', 0))} "
            f"(index {sev.get('escalation_index', 0.0):.2f})."
        )
    valid_a = [e for e in acled_events if isinstance(e, dict) and "error" not in e]
    if valid_a:
        dates = [e.get("date") for e in valid_a if e.get("date")]
        date_range = f" ({min(dates)}–{max(dates)})" if dates else ""
        parts.append(f"ACLED historical: {len(valid_a)} events{date_range}.")
    valid_g = [a for a in gdelt_articles if a.get("title") and "error" not in a]
    if valid_g:
        parts.append(
            f"GDELT: {len(valid_g)} protest articles (72h), avg tone {gdi.get('avg_tone', 0.0):+.2f}, "
            f"keyword hits {int(gdi.get('keyword_hits', 0.0))}."
        )
        if gdi.get("intensity_index", 0.0) >= 1.5:
            parts.append("Media intensity signal elevated (negative tone + escalation keywords).")
    valid_hdx = [h for h in (hdx_events or []) if isinstance(h, dict) and "error" not in h]
    if valid_hdx:
        parts.append(
            f"HDX HAPI: {len(valid_hdx)} conflict rows, fatalities sum {hdi.get('fatalities_sum', 0.0):.0f}, "
            f"VAC rows {int(hdi.get('vac_rows', 0.0))}."
        )
        if hdi.get("intensity_index", 0.0) >= 1.4:
            parts.append("HDX conflict-events confirm elevated on-ground intensity.")
    if gdelt_events_bq and gdelt_events_bq.get("ok") and (gdelt_events_bq.get("total_matched") or 0) > 0:
        tm = int(gdelt_events_bq.get("total_matched") or 0)
        parts.append(
            f"GDELT Events (BQ, {gdelt_events_bq.get('lookback_days', '?')}d): {tm} coded unrest/protest-root events for query."
        )
    if gdelt_gkg_bq and gdelt_gkg_bq.get("ok") and (gdelt_gkg_bq.get("row_count") or 0) > 0:
        parts.append(
            f"GDELT GKG: {gdelt_gkg_bq.get('row_count')} rows; "
            f"protest-theme share {float(gdelt_gkg_bq.get('protest_theme_ratio') or 0):.2f}."
        )
    crisis_ok = [
        p
        for p in (acled_crisis_pages or [])
        if isinstance(p, dict) and not p.get("error") and (p.get("excerpt") or p.get("title"))
    ]
    if crisis_ok:
        parts.append(f"ACLED crisis briefs: {len(crisis_ok)} curated pages scraped.")
    if inform_risk and inform_risk.get("ok") and inform_risk.get("matched"):
        sev = inform_risk.get("max_severity")
        parts.append(
            f"INFORM (HDX): structural severity context for target countries"
            + (f" (max {sev:.2f})." if sev is not None else ".")
        )
    if not parts:
        return "PROTEST: No ACLED or GDELT protest data available."
    return "PROTEST: " + " ".join(parts)


async def _cluster_protest_events_haiku(
    acled_events: List[Dict],
    crisis_pages: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Summarize ACLED API events and/or curated crisis briefs as protest clusters."""
    valid = [e for e in acled_events if isinstance(e, dict) and "error" not in e][:20]
    lines = []
    for i, e in enumerate(valid, 1):
        loc = e.get("location") or e.get("country") or "Unknown"
        etype = e.get("event_type") or e.get("sub_event_type") or "Protest"
        notes = (e.get("notes") or "").strip()[:150]
        lines.append(f"Event {i}: {loc}, {etype}, {notes}")
    for j, p in enumerate((crisis_pages or [])[:10], 1):
        if not isinstance(p, dict) or p.get("error"):
            continue
        ex = (p.get("excerpt") or "").strip()[:220]
        ti = (p.get("title") or p.get("url") or "").strip()[:120]
        if ex or ti:
            lines.append(f"Crisis brief {j}: {ti}. {ex}")
    if not lines:
        return None
    text = (
        "Identify 2-4 protest clusters by geography and cause. For each cluster give: location, "
        "approximate event count, and primary grievance.\n\nSignals:\n" + "\n".join(lines)
    )
    try:
        from services.haiku_service import summarize

        out = await summarize(text[:4000], max_output_tokens=200)
        return out.strip() if out else None
    except Exception:
        return None


def run_protest_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run PROTEST agent: ACLED aggregated + crisis scrape, GDELT DOC/BQ/GKG, HDX HAPI + INFORM."""
    import time

    from .health_registry import get_health_registry
    from .utils import SourceResult, utc_now_iso

    async def _run() -> Dict[str, Any]:
        diagnostics: List[Dict[str, str]] = []

        def _refresh_aggregated_safe() -> None:
            try:
                from services.acled_aggregated import refresh_acled_aggregated

                refresh_acled_aggregated()
            except Exception as e:
                logger.debug("ACLED aggregated refresh skipped: %s", e)

        await asyncio.to_thread(_refresh_aggregated_safe)
        aggregated = await asyncio.to_thread(_load_acled_aggregated, conflict)

        use_acled_api = _use_acled_read_api()

        async def _empty_acled() -> List[Dict[str, Any]]:
            return []

        acled_task = _fetch_acled_protests("", conflict) if use_acled_api else _empty_acled()
        gdelt_task = _fetch_gdelt_protest(conflict)
        hdx_task = _fetch_hdx_hapi_protest(conflict)
        gdelt_bq_task = asyncio.to_thread(fetch_gdelt_protest_events_summary, conflict)
        gkg_task = asyncio.to_thread(_gkg_bq_sync, conflict)
        crisis_task = fetch_acled_crisis_pages_async(conflict)
        inform_task = asyncio.to_thread(fetch_inform_for_iso3, _iso3_from_conflict(conflict))

        (
            acled_events,
            gdelt_articles,
            hdx_events,
            gdelt_events_bq,
            gdelt_gkg_bq,
            acled_crisis_pages,
            inform_risk,
        ) = await asyncio.gather(
            acled_task,
            gdelt_task,
            hdx_task,
            gdelt_bq_task,
            gkg_task,
            crisis_task,
            inform_task,
        )

        if use_acled_api and not has_acled_oauth():
            diagnostics.append(
                {
                    "source": "ACLED-API",
                    "reason": "missing_oauth_credentials",
                    "fix_hint": "Set ACLED_EMAIL and ACLED_PASSWORD in backend/.env.",
                }
            )
        if not use_acled_api:
            diagnostics.append(
                {
                    "source": "ACLED-API",
                    "reason": "disabled",
                    "fix_hint": "Legacy Read-API off (default). Set PROTEST_USE_ACLED_API=1 to enable.",
                }
            )
        if not aggregated.get("weeks"):
            diagnostics.append(
                {
                    "source": "ACLED-Aggregated",
                    "reason": "aggregated_csv_unavailable_or_empty",
                    "fix_hint": "Refresh ACLED aggregated CSV and verify files in backend/data/acled.",
                }
            )
        if _is_acled_stale(acled_events):
            diagnostics.append(
                {
                    "source": "ACLED-API",
                    "reason": "stale_data",
                    "fix_hint": "ACLED API appears older than recent window; scoring shifts to GDELT-primary mode.",
                }
            )
        if _result_is_error_blob(gdelt_articles):
            raw_err = str(gdelt_articles[0].get("error") or "gdelt_error")
            diagnostics.append(
                {
                    "source": "GDELT",
                    "reason": "rate_limited" if "429" in raw_err else "request_failed",
                    "fix_hint": "Retry later for rate limits; otherwise verify outbound access to api.gdeltproject.org.",
                }
            )
        if not HAPI_APP_IDENTIFIER:
            diagnostics.append(
                {
                    "source": "HDX HAPI",
                    "reason": "missing_hapi_app_identifier",
                    "fix_hint": "Set HAPI_APP_IDENTIFIER in backend/.env to enable HDX HAPI.",
                }
            )
        elif _result_is_error_blob(hdx_events):
            diagnostics.append(
                {
                    "source": "HDX HAPI",
                    "reason": "request_failed",
                    "fix_hint": "Verify app identifier and access to hapi.humdata.org.",
                }
            )
        if not gdelt_events_bq.get("ok"):
            diagnostics.append(
                {
                    "source": "GDELT-Events-BQ",
                    "reason": str(gdelt_events_bq.get("reason") or gdelt_events_bq.get("error") or "skipped_or_failed"),
                    "fix_hint": "Enable GDELT_BQ_ENABLED, install google-cloud-bigquery, set GCP credentials.",
                }
            )
        if not gdelt_gkg_bq.get("ok"):
            diagnostics.append(
                {
                    "source": "GDELT-GKG-BQ",
                    "reason": str(gdelt_gkg_bq.get("reason") or gdelt_gkg_bq.get("error") or "skipped_or_failed"),
                    "fix_hint": "Same as Events-BQ; set PROTEST_GKG_BQ_ENABLED=0 to silence GKG attempts.",
                }
            )
        crisis_ok_n = len(
            [
                p
                for p in (acled_crisis_pages or [])
                if isinstance(p, dict) and not p.get("error") and (p.get("excerpt") or p.get("title"))
            ]
        )
        if crisis_ok_n == 0:
            diagnostics.append(
                {
                    "source": "ACLED-Crisis",
                    "reason": "no_pages",
                    "fix_hint": "Check ACLED_CRISIS_HUB_URLS and outbound access to acleddata.com.",
                }
            )
        if not inform_risk.get("ok"):
            diagnostics.append(
                {
                    "source": "INFORM-HDX",
                    "reason": str(inform_risk.get("reason") or inform_risk.get("error") or "fetch_failed"),
                    "fix_hint": "Set INFORM_HDX_PACKAGE if the default CKAN slug changed; ensure openpyxl installed.",
                }
            )

        protest_score, score_breakdown = _compute_protest_score(
            acled_events,
            gdelt_articles,
            hdx_events,
            aggregated,
            gdelt_events_bq=gdelt_events_bq,
            gdelt_gkg_bq=gdelt_gkg_bq,
            acled_crisis_pages=acled_crisis_pages,
            inform_risk=inform_risk,
        )
        dynamic_metrics = _compute_dynamic_baseline_metrics(aggregated)
        severity_mix = _compute_event_severity_mix(acled_events)
        gdelt_intensity = _compute_gdelt_intensity_metrics(gdelt_articles)
        hdx_intensity = _compute_hdx_intensity_metrics(hdx_events)
        base_summary = _build_summary(
            acled_events,
            gdelt_articles,
            hdx_events,
            protest_score,
            aggregated,
            gdelt_events_bq=gdelt_events_bq,
            gdelt_gkg_bq=gdelt_gkg_bq,
            acled_crisis_pages=acled_crisis_pages,
            inform_risk=inform_risk,
        )
        cluster_summary = await _cluster_protest_events_haiku(acled_events, acled_crisis_pages)
        if cluster_summary:
            summary = f"{base_summary} Clusters: {cluster_summary}"
        else:
            summary = base_summary
        return {
            "protest_score": round(protest_score, 1),
            "score_breakdown": score_breakdown,
            "protest_events": acled_events,
            "protest_articles": gdelt_articles,
            "hdx_conflict_events": hdx_events,
            "acled_aggregated": aggregated,
            "dynamic_metrics": dynamic_metrics,
            "severity_mix": severity_mix,
            "gdelt_intensity": gdelt_intensity,
            "hdx_intensity": hdx_intensity,
            "gdelt_events_bigquery": gdelt_events_bq,
            "gdelt_gkg_bigquery": gdelt_gkg_bq,
            "acled_crisis_pages": acled_crisis_pages,
            "inform_risk": inform_risk,
            "diagnostics": diagnostics,
            "summary": summary,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run(), timeout_s=PROTEST_ASYNC_TIMEOUT_S)
        duration_ms = int((time.perf_counter() - start) * 1000)
        events = out.get("protest_events") or []
        articles = out.get("protest_articles") or []
        hdx_rows = out.get("hdx_conflict_events") or []
        agg = out.get("acled_aggregated") or {}
        diagnostics = out.get("diagnostics") or []
        gdelt_ev_bq = out.get("gdelt_events_bigquery") or {}
        gdelt_gkg = out.get("gdelt_gkg_bigquery") or {}
        crisis_pages = out.get("acled_crisis_pages") or []
        inform_rr = out.get("inform_risk") or {}

        acled_error_blob = _result_is_error_blob(events)
        gdelt_error_blob = _result_is_error_blob(articles)
        hdx_error_blob = _result_is_error_blob(hdx_rows)

        use_api = _use_acled_read_api()
        acled_ok = bool(use_api and events and not acled_error_blob)
        crisis_ok_n = len(
            [
                p
                for p in crisis_pages
                if isinstance(p, dict) and not p.get("error") and (p.get("excerpt") or p.get("title"))
            ]
        )
        gdelt_ok = bool(articles and not gdelt_error_blob)
        hdx_ok = bool(hdx_rows and not hdx_error_blob)
        agg_ok = bool(agg.get("weeks"))
        bq_ev_ok = bool(gdelt_ev_bq.get("ok") and int(gdelt_ev_bq.get("total_matched") or 0) > 0)
        gkg_ok = bool(gdelt_gkg.get("ok") and int(gdelt_gkg.get("row_count") or 0) > 0)
        inform_ok = bool(inform_rr.get("ok") and inform_rr.get("match_count", 0) > 0)
        source_results = [
            SourceResult(
                name="ACLED-Aggregated",
                status="ok" if agg_ok else "degraded",
                fetched_at=fetched_at,
                record_count=agg.get("total_events_4w", 0),
                error=None if agg_ok else "aggregated_csv_unavailable_or_empty",
            ),
            SourceResult(
                name="ACLED-API",
                status=(
                    "ok"
                    if acled_ok
                    else ("degraded" if use_api else "degraded")
                ),
                fetched_at=fetched_at,
                record_count=len(events) if not acled_error_blob else 0,
                error=(
                    None
                    if acled_ok
                    else (
                        "protest_use_acled_api_disabled"
                        if not use_api
                        else (
                            "missing_oauth_credentials"
                            if not has_acled_oauth()
                            else "no_events_returned_or_request_failed"
                        )
                    )
                ),
            ),
            SourceResult(
                name="ACLED-Crisis",
                status="ok" if crisis_ok_n > 0 else "degraded",
                fetched_at=fetched_at,
                record_count=crisis_ok_n,
                error=None if crisis_ok_n > 0 else "no_crisis_pages",
            ),
            SourceResult(
                name="GDELT",
                status="ok" if gdelt_ok else ("error" if gdelt_error_blob else "degraded"),
                fetched_at=fetched_at,
                record_count=len(articles) if not gdelt_error_blob else 0,
                error=(
                    None
                    if gdelt_ok
                    else (
                        str(articles[0].get("error") or "gdelt_request_failed")
                        if gdelt_error_blob
                        else "no_articles_returned"
                    )
                ),
            ),
            SourceResult(
                name="GDELT-Events-BQ",
                status="ok" if bq_ev_ok else "degraded",
                fetched_at=fetched_at,
                record_count=int(gdelt_ev_bq.get("total_matched") or 0) if bq_ev_ok else 0,
                error=(
                    None
                    if bq_ev_ok
                    else str(gdelt_ev_bq.get("reason") or gdelt_ev_bq.get("error") or "no_bigquery_hits")
                ),
            ),
            SourceResult(
                name="GDELT-GKG-BQ",
                status="ok" if gkg_ok else "degraded",
                fetched_at=fetched_at,
                record_count=int(gdelt_gkg.get("row_count") or 0) if gkg_ok else 0,
                error=(
                    None
                    if gkg_ok
                    else str(gdelt_gkg.get("reason") or gdelt_gkg.get("error") or "no_bigquery_hits")
                ),
            ),
            SourceResult(
                name="HDX HAPI",
                status=("ok" if hdx_ok else ("error" if hdx_error_blob else "degraded")),
                fetched_at=fetched_at,
                record_count=len(hdx_rows) if not hdx_error_blob else 0,
                error=(
                    None
                    if hdx_ok
                    else (
                        str(hdx_rows[0].get("error") or "hdx_request_failed")
                        if hdx_error_blob
                        else ("missing_hapi_app_identifier" if not HAPI_APP_IDENTIFIER else "no_rows_returned")
                    )
                ),
            ),
            SourceResult(
                name="INFORM-HDX",
                status="ok" if inform_ok else "degraded",
                fetched_at=fetched_at,
                record_count=int(inform_rr.get("match_count") or 0) if inform_ok else 0,
                error=None if inform_ok else str(inform_rr.get("error") or inform_rr.get("reason") or "no_inform_rows"),
            ),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "protest", sr)
        has_data = bool(
            events
            or articles
            or agg.get("weeks")
            or bq_ev_ok
            or gkg_ok
            or crisis_ok_n
            or inform_ok
        )
        out["_meta"] = build_agent_meta("protest", fetched_at, duration_ms, source_results, has_any_data=has_data)
        out["diagnostics"] = diagnostics
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fallback = get_agent_fallback("protest")
        fallback["conflict"] = conflict
        fallback["summary"] = f"PROTEST error: {e}"
        fallback["_meta"] = build_agent_meta(
            "protest", fetched_at, duration_ms, [], fallback_used=True, error_summary=str(e), has_any_data=False
        )
        return fallback
