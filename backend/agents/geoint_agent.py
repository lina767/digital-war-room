"""
GEOINT Agent – LangChain Tool-Calling Agent
Detects thermal anomalies via NASA FIRMS in conflict regions.
Uses area-specific API (no world download). Supplemented by ReliefWeb/ACLED, UCDP (Uppsala) event data.
"""
import asyncio
import csv
import io
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import httpx
from .llm_factory import get_agent_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

# Format: /api/area/csv/{key}/{source}/{area}/{days} — area = "W,S,E,N" (lon_min, lat_min, lon_max, lat_max)
FIRMS_AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{area}/{days}"

# Bounding boxes for FIRMS area API (W,S,E,N = lon_min, lat_min, lon_max, lat_max)
REGION_BBOX = {
    "middle_east": "35,20,65,40",
    "eastern_europe": "22,44,40,55",
    "east_asia": "100,20,130,45",
    "africa": "20,-5,45,25",
    "gaza_israel": "34,29,36,34",
    "iran": "44,24,64,40",
    "yemen": "42,12,56,20",
}

# For in-memory bbox filter (lat_min, lat_max, lon_min, lon_max) derived from REGION_BBOX
def _bbox_to_region(area: str) -> Dict[str, float]:
    parts = [float(x.strip()) for x in area.split(",")]
    if len(parts) != 4:
        return {"lat_min": 20, "lat_max": 40, "lon_min": 35, "lon_max": 65}
    lon_min, lat_min, lon_max, lat_max = parts
    return {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}

REGIONS = {k: _bbox_to_region(v) for k, v in REGION_BBOX.items()}

# When querying middle_east, also fetch these sub-regions and combine
SUB_REGIONS_FOR_REGION = {
    "middle_east": ["middle_east", "gaza_israel", "iran", "yemen"],
    "eastern_europe": ["eastern_europe"],
    "east_asia": ["east_asia"],
    "africa": ["africa"],
    "gaza_israel": ["gaza_israel"],
    "iran": ["iran"],
    "yemen": ["yemen"],
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _confidence(raw: Any) -> str:
    if raw is None:
        return "low"
    s = str(raw).strip().upper()
    if s in ("HIGH", "H"):
        return "high"
    if s in ("NOMINAL", "N"):
        return "nominal"
    try:
        v = float(raw)
        return "high" if v >= 80 else "nominal" if v >= 40 else "low"
    except (TypeError, ValueError):
        return "low"


def _classify(frp: float) -> str:
    if frp > 1000:
        return "explosion"
    if frp > 500:
        return "explosion"  # military explosions typically > 500 MW, wildfires 50-200 MW
    if frp >= 100:
        return "fire"
    return "unknown"


def _is_explosion_cluster(anomalies: List[Dict[str, Any]], radius_deg: float = 0.5) -> List[Dict[str, Any]]:
    """Detect clusters of anomalies (within radius_deg) indicating possible military activity."""
    clusters = []
    used = set()
    for a in anomalies:
        lat = _safe_float(a.get("lat"), 0)
        lon = _safe_float(a.get("lon"), 0)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        nearby = [
            b for b in anomalies
            if abs(_safe_float(b.get("lat"), 0) - lat) <= radius_deg
            and abs(_safe_float(b.get("lon"), 0) - lon) <= radius_deg
        ]
        if len(nearby) >= 3:
            used.add(key)
            clusters.append({
                "center_lat": round(lat, 4),
                "center_lon": round(lon, 4),
                "count": len(nearby),
            })
    return clusters


def _parse_firms_row(row: dict, bbox: dict) -> dict | None:
    """Parse one FIRMS CSV row into anomaly dict; return None if outside bbox."""
    lat = _safe_float(row.get("latitude") or row.get("lat"))
    lon = _safe_float(row.get("longitude") or row.get("lon"))
    if not (bbox["lat_min"] <= lat <= bbox["lat_max"]):
        return None
    if not (bbox["lon_min"] <= lon <= bbox["lon_max"]):
        return None
    frp = _safe_float(row.get("frp"))
    conf = _confidence(row.get("confidence"))
    acq_date = row.get("acq_date", "")
    acq_time = row.get("acq_time", "")
    t = str(acq_time).strip()
    if len(t) == 4 and t.isdigit():
        t = f"{t[:2]}:{t[2:]}"
    acquired = f"{acq_date}T{t}Z" if acq_date else ""
    return {
        "lat": lat, "lon": lon,
        "frp": frp,
        "confidence": conf,
        "type": _classify(frp),
        "acquired": acquired,
    }


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def get_thermal_anomalies(region: str = "middle_east", days: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch NASA FIRMS thermal anomalies for a region (area API, no world download).
    Region options: middle_east, eastern_europe, east_asia, africa, gaza_israel, iran, yemen.
    For middle_east, also queries gaza_israel, iran, yemen and combines (deduped by lat,lon).
    Days: 1-5 (default 3 for better coverage despite cloud cover).
    """
    api_key = os.getenv("NASA_FIRMS_KEY")
    if not api_key:
        return [{"error": "NASA_FIRMS_KEY not set"}]

    days = max(1, min(5, int(days)))
    areas_to_fetch = SUB_REGIONS_FOR_REGION.get(region, [region])
    # Ensure we have bbox for each area
    areas_to_fetch = [a for a in areas_to_fetch if a in REGION_BBOX]

    async def _fetch_one(area: str) -> str:
        bbox_str = REGION_BBOX[area]
        url = FIRMS_AREA_URL.format(key=api_key, area=bbox_str, days=days)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    try:
        all_anomalies = []
        for area in areas_to_fetch:
            try:
                csv_text = asyncio.run(_fetch_one(area))
                bbox = REGIONS.get(area, REGIONS["middle_east"])
                reader = csv.DictReader(io.StringIO(csv_text))
                for row in reader:
                    a = _parse_firms_row(row, bbox)
                    if a:
                        all_anomalies.append(a)
            except Exception:
                continue
        # Deduplicate by (lat, lon) rounded to 2 decimals
        seen = set()
        deduped = []
        for a in all_anomalies:
            key = (round(_safe_float(a.get("lat"), 0), 2), round(_safe_float(a.get("lon"), 0), 2))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(a)
        return deduped
    except Exception as e:
        return [{"error": str(e)}]


@tool
def get_conflict_region(conflict: str) -> str:
    """Map a conflict name to its geographic region for thermal anomaly detection."""
    cl = conflict.lower()
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria", "iraq"]):
        return "middle_east"
    if any(k in cl for k in ["ukraine", "russia", "donbas", "belarus"]):
        return "eastern_europe"
    if any(k in cl for k in ["taiwan", "china", "korea", "myanmar"]):
        return "east_asia"
    if any(k in cl for k in ["sudan", "ethiopia", "drc", "sahel", "mali"]):
        return "africa"
    return "middle_east"


# ReliefWeb API v2: filter by country name (e.g. "Iran", "Ukraine"). appname required.
RELIEFWEB_APPNAME = "digital-war-room"
RELIEFWEB_COUNTRY_NAMES = {
    "iran": ["Iran"],
    "israel": ["Israel"],
    "gaza": ["State of Palestine", "Israel"],
    "yemen": ["Yemen"],
    "syria": ["Syria"],
    "iraq": ["Iraq"],
    "ukraine": ["Ukraine"],
    "russia": ["Russian Federation"],
    "default": ["Iran", "Syria", "Yemen", "State of Palestine", "Israel"],
}

# ACLED API: filter by country name (e.g. "Iran", "Ukraine"). Requires ACLED_API_KEY (+ optional ACLED_EMAIL).
ACLED_COUNTRY_NAMES = {
    "iran": "Iran",
    "israel": "Israel",
    "gaza": "Palestine",
    "yemen": "Yemen",
    "syria": "Syria",
    "iraq": "Iraq",
    "ukraine": "Ukraine",
    "russia": "Russia",
    "default": "Iran",
}


@tool
def get_conflict_hotspot_news(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent geospatial event reports from ReliefWeb API v2 (free, no key) and optionally ACLED.
    ReliefWeb: filter by country name; returns title, date, body excerpt, source.
    ACLED: optional, uses country name; requires ACLED_API_KEY (and ACLED_EMAIL if needed).
    """
    cl = conflict.lower()
    rw_countries = next(
        (v for k, v in RELIEFWEB_COUNTRY_NAMES.items() if k != "default" and k in cl),
        RELIEFWEB_COUNTRY_NAMES["default"],
    )
    acled_country = next(
        (v for k, v in ACLED_COUNTRY_NAMES.items() if k != "default" and k in cl),
        ACLED_COUNTRY_NAMES["default"],
    )

    async def _reliefweb() -> List[Dict[str, Any]]:
        reports = []
        # ReliefWeb v2: filter[field]=country&filter[value]=CountryName; multiple with filter[value][]=A&filter[value][]=B&filter[operator]=OR
        for country_name in rw_countries[:3]:
            try:
                url = "https://api.reliefweb.int/v2/reports"
                params = {
                    "appname": RELIEFWEB_APPNAME,
                    "limit": 10,
                    "filter[field]": "country",
                    "filter[value]": country_name,
                    "preset": "latest",
                    "fields[include][]": ["title", "date", "body", "source.name", "country.name"],
                }
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                items = data.get("data", [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    fields = item.get("fields", {})
                    if not isinstance(fields, dict):
                        continue
                    title = (fields.get("title") or "")[:300]
                    date_obj = fields.get("date") or {}
                    if isinstance(date_obj, dict):
                        date_created = date_obj.get("created") or date_obj.get("changed") or ""
                    else:
                        date_created = str(date_obj)[:30]
                    body_raw = fields.get("body") or ""
                    if isinstance(body_raw, str):
                        body_excerpt = body_raw[:200]
                    else:
                        body_excerpt = ""
                    src_list = fields.get("source") or []
                    if src_list and isinstance(src_list[0], dict):
                        source = src_list[0].get("name", "")
                    else:
                        source = "ReliefWeb"
                    country_list = fields.get("country") or []
                    country_display = country_list[0].get("name", country_name) if country_list and isinstance(country_list[0], dict) else country_name
                    reports.append({
                        "title": title,
                        "date": date_created,
                        "body_excerpt": body_excerpt,
                        "source": source,
                        "country": country_display,
                    })
            except Exception:
                continue
        return reports[:15]

    try:
        reports = asyncio.run(_reliefweb())
    except Exception as e:
        reports = [{"error": str(e)}]

    acled_key = os.getenv("ACLED_API_KEY")
    if acled_key and isinstance(reports, list) and not any(isinstance(r, dict) and r.get("error") for r in reports):
        try:
            url = "https://api.acleddata.com/acled/read"
            params = {
                "key": acled_key,
                "limit": 10,
                "country": acled_country,
            }
            email = os.getenv("ACLED_EMAIL")
            if email:
                params["email"] = email
            async def _acled():
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code != 200:
                        return
                    data = resp.json()
                    for rec in (data.get("data") or [])[:10]:
                        if isinstance(rec, dict):
                            reports.append({
                                "title": (rec.get("event") or rec.get("title") or "")[:300],
                                "date": rec.get("event_date", ""),
                                "body_excerpt": (rec.get("notes") or "")[:200],
                                "source": "ACLED",
                                "country": rec.get("country", acled_country),
                            })
            asyncio.run(_acled())
        except Exception:
            pass
    return reports if isinstance(reports, list) else [{"error": "unknown"}]


# ── EO Browser / Sentinel Hub (links; optional Process API when credentials set) ─

# EO Browser: center (lat, lon), zoom. No API key required – returns URLs for manual inspection.
EO_BROWSER_VIEWS = {
    "iran": (32.5, 53.0, 5),
    "lebanon": (33.9, 35.5, 8),
    "gaza_israel": (31.5, 34.5, 8),
    "middle_east": (30.0, 50.0, 4),
    "yemen": (15.5, 48.0, 6),
    "syria": (35.0, 38.5, 6),
    "ukraine": (49.0, 32.0, 5),
    "eastern_europe": (49.0, 32.0, 5),
}


def _region_from_conflict(conflict: str) -> str:
    """Region slug for EO Browser / Liveuamap (iran, lebanon, middle_east, etc.)."""
    cl = conflict.lower()
    if "lebanon" in cl:
        return "lebanon"
    if "iran" in cl:
        return "iran"
    if any(k in cl for k in ["gaza", "israel"]):
        return "gaza_israel"
    if any(k in cl for k in ["yemen", "syria", "iraq"]):
        return "middle_east"
    if any(k in cl for k in ["ukraine", "russia", "donbas", "belarus"]):
        return "eastern_europe"
    if any(k in cl for k in ["taiwan", "china", "korea", "myanmar"]):
        return "east_asia"
    if any(k in cl for k in ["sudan", "ethiopia", "drc", "sahel", "mali"]):
        return "africa"
    return "middle_east"


# UCDP API: https://ucdpapi.pcr.uu.se/api/<resource>/<version>?pagesize=x&page=x [&Country=country_id][&StartDate=][&EndDate=]
# Requires UCDP_API_TOKEN (header: x-ucdp-access-token). Gleditsch & Ward country_id.
UCDP_BASE = "https://ucdpapi.pcr.uu.se/api"
UCDP_GED_VERSION = "25.1"
UCDP_COUNTRY_IDS = {
    "iran": [630],  # Iran (GW)
    "iraq": [645], "syria": [652], "yemen": [679], "israel": [666], "gaza": [667],
    "ukraine": [369], "russia": [365], "libya": [620], "sudan": [625], "afghanistan": [700],
    "default": [630],
}


@tool
def get_ucdp_events(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent conflict events from UCDP GED (Uppsala Conflict Data Program).
    API: ucdpapi.pcr.uu.se/api/gedevents/25.1. Requires UCDP_API_TOKEN (x-ucdp-access-token).
    Returns events for the conflict country (e.g. Iran=630); optional StartDate/EndDate for last 90 days.
    """
    token = (os.getenv("UCDP_API_TOKEN") or os.getenv("UCDP_ACCESS_TOKEN") or "").strip()
    if not token:
        return []

    cl = conflict.lower()
    country_ids = next((v for k, v in UCDP_COUNTRY_IDS.items() if k != "default" and k in cl), UCDP_COUNTRY_IDS["default"])
    country_id = country_ids[0] if country_ids else 630

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=90)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    async def _fetch():
        events = []
        try:
            url = f"{UCDP_BASE}/gedevents/{UCDP_GED_VERSION}"
            params = {"pagesize": 50, "page": 1, "Country": country_id, "StartDate": start_str, "EndDate": end_str}
            headers = {"x-ucdp-access-token": token}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                result = data.get("Result", [])
                if not isinstance(result, list):
                    return []
                for e in result:
                    if not isinstance(e, dict):
                        continue
                    events.append({
                        "id": e.get("id"),
                        "country": e.get("country"),
                        "date_start": e.get("date_start"),
                        "date_end": e.get("date_end"),
                        "side_a": e.get("side_a"),
                        "side_b": e.get("side_b"),
                        "deaths_a": e.get("deaths_a"),
                        "deaths_b": e.get("deaths_b"),
                        "deaths_civilians": e.get("deaths_civilians"),
                        "best": e.get("best"),
                        "type_of_violence": e.get("type_of_violence"),
                        "latitude": e.get("latitude"),
                        "longitude": e.get("longitude"),
                    })
        except Exception:
            pass
        return events

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []


@tool
def get_eo_browser_links(conflict: str) -> Dict[str, Any]:
    """
    Return direct links to Sentinel Hub EO Browser for the conflict region (Lebanon, Iran, etc.).
    No API key required. Use for manual satellite imagery inspection (Sentinel-2, etc.).
    """
    region = _region_from_conflict(conflict)
    # Prefer region-specific view if available
    view = EO_BROWSER_VIEWS.get(region) or EO_BROWSER_VIEWS["middle_east"]
    lat, lon, zoom = view
    base = "https://apps.sentinel-hub.com/eo-browser"
    url = f"{base}/?lat={lat}&lng={lon}&zoom={zoom}"
    return {
        "region": region,
        "eo_browser_url": url,
        "description": "Open in EO Browser for Sentinel-2 and other satellite imagery. Sentinel Hub Process API can be enabled with SENTINELHUB_CLIENT_ID and SENTINELHUB_CLIENT_SECRET.",
    }


# ── Agent ──────────────────────────────────────────────────────────────────

GEOINT_TOOLS = [get_conflict_region, get_thermal_anomalies, get_conflict_hotspot_news, get_ucdp_events, get_eo_browser_links]

GEOINT_SYSTEM = """You are a GEOINT (Geospatial Intelligence) analyst using NASA FIRMS, ReliefWeb/ACLED, UCDP (Uppsala), and EO Browser links.
Your job: get conflict region, fetch thermal anomalies (days=3), conflict hotspot news, UCDP events (if token set), and EO Browser links for the region (Lebanon, Iran, etc.); then compute score.

Steps:
1. Call get_conflict_region(conflict)
2. Call get_thermal_anomalies(region=..., days=3)
3. Call get_conflict_hotspot_news(conflict)
4. Call get_ucdp_events(conflict) for Uppsala conflict event data (optional)
5. Call get_eo_browser_links(conflict) for Sentinel Hub EO Browser URLs
6. Compute score and return JSON

Scoring:
- Base: 20
- High-confidence anomaly: +5 each (max +40)
- Explosion-type (FRP>500): +15 each (max +45)
- Cluster (3+ anomalies within 0.5°): +20
- Recent (acquired within last 6h): +5 per anomaly
- More than 10 anomalies: +10
- Clamp to [0, 100]

Return ONLY valid JSON:
{
  "anomalies": [...],
  "anomaly_count": <number>,
  "high_confidence_count": <number>,
  "explosion_count": <number>,
  "clusters": [{"center_lat": ..., "center_lon": ..., "count": N}],
  "geoint_score": <number>,
  "hotspots": [top 5 by FRP],
  "reliefweb_reports": [...],
  "eo_browser_links": {"region": "...", "eo_browser_url": "...", "description": "..."},
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


def _recent_within_hours(acquired_str: str, hours: float = 6.0) -> bool:
    """True if acquired_str (e.g. 2024-01-15T12:30Z or 2024-01-15T1230Z) is within last hours."""
    if not acquired_str or not isinstance(acquired_str, str):
        return False
    try:
        s = acquired_str.strip().replace("Z", "+00:00")
        if "T" in s:
            date_part, time_part = s.split("T", 1)
            time_part = time_part.replace("+00:00", "").replace("-", "").replace(":", "").strip()[:6]
            if len(time_part) >= 4 and ":" not in time_part:
                time_part = f"{time_part[:2]}:{time_part[2:4]}:00"
            s = f"{date_part}T{time_part}+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() <= hours * 3600
    except Exception:
        return False


def _compute_geoint_score(anomalies: List[Dict[str, Any]]) -> Tuple[float, int, List[Dict], int]:
    """Returns (score, explosion_count, clusters, recent_count)."""
    high = sum(1 for a in anomalies if a.get("confidence") == "high")
    explosion_count = sum(1 for a in anomalies if a.get("type") == "explosion" or _safe_float(a.get("frp"), 0) > 500)
    clusters = _is_explosion_cluster(anomalies, radius_deg=0.5)
    recent = sum(1 for a in anomalies if _recent_within_hours(a.get("acquired", ""), 6.0))
    base = 20.0
    base += min(40, high * 5)
    base += min(45, explosion_count * 15)
    if clusters:
        base += 20
    base += recent * 5
    if len(anomalies) > 10:
        base += 10
    return (max(0.0, min(100.0, base)), explosion_count, clusters, recent)


def _empty_result(conflict: str) -> Dict[str, Any]:
    return {
        "conflict": conflict,
        "anomalies": [],
        "anomaly_count": 0,
        "high_confidence_count": 0,
        "explosion_count": 0,
        "clusters": [],
        "geoint_score": 20.0,
        "hotspots": [],
        "reliefweb_reports": [],
        "ucdp_events": [],
        "eo_browser_links": {},
        "summary": "No thermal anomaly data available.",
    }


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_geoint(conflict: str) -> Dict[str, Any]:
    """Execute GEOINT tool chain: region → thermal_anomalies → hotspot_news → ucdp_events → eo_browser_links. No LLM."""
    try:
        region = get_conflict_region.invoke({"conflict": conflict})
        if not isinstance(region, str):
            region = "middle_east"
        raw = get_thermal_anomalies.invoke({"region": region, "days": 3})
        anomalies = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
        reliefweb_raw = get_conflict_hotspot_news.invoke({"conflict": conflict})
        reliefweb_reports = [r for r in (reliefweb_raw if isinstance(reliefweb_raw, list) else []) if isinstance(r, dict) and "error" not in r]
        ucdp_raw = get_ucdp_events.invoke({"conflict": conflict})
        ucdp_events = [e for e in (ucdp_raw if isinstance(ucdp_raw, list) else []) if isinstance(e, dict) and "error" not in e]
        eo_links = get_eo_browser_links.invoke({"conflict": conflict})
        if not isinstance(eo_links, dict):
            eo_links = {}
        score, explosion_count, clusters, _ = _compute_geoint_score(anomalies)
        if ucdp_events:
            score = min(100.0, score + min(15, len(ucdp_events) * 2))
        high = sum(1 for a in anomalies if a.get("confidence") == "high")
        hotspots = sorted(anomalies, key=lambda x: _safe_float(x.get("frp"), 0), reverse=True)[:5]
        summary_extra = f" {len(ucdp_events)} UCDP events." if ucdp_events else ""
        return {
            "conflict": conflict,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "high_confidence_count": high,
            "explosion_count": explosion_count,
            "clusters": clusters,
            "geoint_score": round(score, 1),
            "hotspots": hotspots,
            "reliefweb_reports": reliefweb_reports,
            "ucdp_events": ucdp_events,
            "eo_browser_links": eo_links,
            "summary": f"GEOINT (rule-based): {len(anomalies)} thermal anomalies ({high} high conf, {explosion_count} explosion-type). {len(clusters)} cluster(s).{summary_extra} EO Browser links included. Score {score:.0f}.",
        }
    except Exception:
        pass
    return _empty_result(conflict)


def run_geoint_agent(conflict: str) -> Dict[str, Any]:
    """Run GEOINT: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    import json
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_geoint(conflict)

    model = get_agent_model(GEOINT_TOOLS)

    messages = [
        SystemMessage(content=GEOINT_SYSTEM),
        HumanMessage(content=f"Detect thermal anomalies for conflict: {conflict}"),
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
            tool_map = {t.name: t for t in GEOINT_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                args = dict(tc.get("args", {}))
                if "conflict" not in args and tool_fn.name in ("get_conflict_region", "get_conflict_hotspot_news", "get_ucdp_events"):
                    args["conflict"] = conflict
                result = tool_fn.invoke(args)
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    # Fallback: same fixed tool chain as rule-based mode
    return _run_rule_based_geoint(conflict)
