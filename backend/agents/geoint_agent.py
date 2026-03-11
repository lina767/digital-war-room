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
from services.acled_auth import get_acled_token_async, has_acled_oauth
from .llm import run_tool_agent

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


# Static list of known gas flaring / industrial sites (approximate) to down-weight in GEOINT.
# These are approximate centroids of major oil/gas fields with persistent flares.
GAS_FLARE_SITES: List[Dict[str, Any]] = [
    {"name": "South Pars gas field", "lat": 26.5, "lon": 52.5, "radius_deg": 0.3},
    {"name": "Rumaila oil field", "lat": 30.7, "lon": 47.5, "radius_deg": 0.3},
    {"name": "Kirkuk oil field", "lat": 35.6, "lon": 44.3, "radius_deg": 0.3},
]


def _is_gas_flare_site(lat: float, lon: float) -> bool:
    for site in GAS_FLARE_SITES:
        r = float(site.get("radius_deg", 0.3))
        if abs(lat - float(site["lat"])) <= r and abs(lon - float(site["lon"])) <= r:
            return True
    return False


def _is_explosion_cluster(
    anomalies: List[Dict[str, Any]],
    radius_deg: float = 0.5,
    max_hours: float | None = 2.0,
) -> List[Dict[str, Any]]:
    """
    Detect clusters of anomalies (within radius_deg and optional time window) indicating possible
    military activity. Gas-flaring / industrial sites are ignored.
    """
    clusters = []
    used = set()
    for a in anomalies:
        if a.get("gas_flaring"):
            continue
        lat = _safe_float(a.get("lat"), 0)
        lon = _safe_float(a.get("lon"), 0)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        nearby: List[Dict[str, Any]] = []
        t0 = None
        if max_hours is not None:
            # Parse acquisition time for temporal clustering; ignore if parsing fails.
            from datetime import datetime as _dt

            def _parse_t(acq: str) -> Any:
                if not acq:
                    return None
                s = str(acq).strip().replace("Z", "+00:00")
                try:
                    return _dt.fromisoformat(s)
                except Exception:
                    return None

            t0 = _parse_t(a.get("acquired", ""))
            for b in anomalies:
                if b.get("gas_flaring"):
                    continue
                if abs(_safe_float(b.get("lat"), 0) - lat) > radius_deg:
                    continue
                if abs(_safe_float(b.get("lon"), 0) - lon) > radius_deg:
                    continue
                if t0 is not None and max_hours is not None:
                    tb = _parse_t(b.get("acquired", ""))
                    if tb is None:
                        continue
                    if abs((tb - t0).total_seconds()) > max_hours * 3600:
                        continue
                nearby.append(b)
        else:
            nearby = [
                b for b in anomalies
                if not b.get("gas_flaring")
                and abs(_safe_float(b.get("lat"), 0) - lat) <= radius_deg
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
    is_flaring = _is_gas_flare_site(lat, lon)
    ftype = "industrial" if is_flaring else _classify(frp)
    return {
        "lat": lat, "lon": lon,
        "frp": frp,
        "confidence": conf,
        "type": ftype,
        "gas_flaring": is_flaring,
        "acquired": acquired,
    }


# ── Tools ──────────────────────────────────────────────────────────────────

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

    async def _fetch_one(area: str) -> tuple[str, str]:
        """Returns (area, csv_text). On error returns (area, '')."""
        bbox_str = REGION_BBOX[area]
        url = FIRMS_AREA_URL.format(key=api_key, area=bbox_str, days=days)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return (area, resp.text)

    async def _fetch_all() -> List[Dict[str, Any]]:
        tasks = [_fetch_one(area) for area in areas_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_anomalies = []
        for r in results:
            if isinstance(r, Exception):
                continue
            area, csv_text = r
            if not csv_text:
                continue
            bbox = REGIONS.get(area, REGIONS["middle_east"])
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                a = _parse_firms_row(row, bbox)
                if a:
                    all_anomalies.append(a)
        return all_anomalies

    try:
        all_anomalies = asyncio.run(_fetch_all())
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


def get_conflict_region(conflict: str) -> str:
    """Map a conflict name to its geographic region for thermal anomaly detection."""
    cl = conflict.lower()
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria", "iraq", "lebanon"]):
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
    "lebanon": ["Lebanon"],
    "syria": ["Syria"],
    "iraq": ["Iraq"],
    "ukraine": ["Ukraine"],
    "russia": ["Russian Federation"],
    "default": ["Iran", "Syria", "Yemen", "State of Palestine", "Israel"],
}

# ACLED API: OAuth (ACLED_EMAIL + ACLED_PASSWORD) at acleddata.com/api; legacy key at api.acleddata.com
ACLED_API_URL = "https://acleddata.com/api/acled/read"
ACLED_LEGACY_URL = "https://api.acleddata.com/acled/read"

# ACLED API: filter by country name (e.g. "Iran", "Ukraine"). OAuth or legacy ACLED_API_KEY.
ACLED_COUNTRY_NAMES = {
    "iran": "Iran",
    "israel": "Israel",
    "gaza": "Palestine",
    "yemen": "Yemen",
    "lebanon": "Lebanon",
    "syria": "Syria",
    "iraq": "Iraq",
    "ukraine": "Ukraine",
    "russia": "Russia",
    "default": "Iran",
}


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

    acled_ok = has_acled_oauth() or os.getenv("ACLED_API_KEY")
    if acled_ok and isinstance(reports, list) and not any(isinstance(r, dict) and r.get("error") for r in reports):
        try:
            async def _acled():
                token = await get_acled_token_async() if has_acled_oauth() else None
                if has_acled_oauth() and not token:
                    return
                params = {"_format": "json", "limit": 10, "country": acled_country}
                if token:
                    url = ACLED_API_URL
                    headers = {"Authorization": f"Bearer {token}"}
                else:
                    url = ACLED_LEGACY_URL
                    headers = {}
                    params["key"] = os.getenv("ACLED_API_KEY", "")
                    if os.getenv("ACLED_EMAIL"):
                        params["email"] = os.getenv("ACLED_EMAIL", "")
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.get(url, params=params, headers=headers)
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


def get_conflict_events_for_heatmap(conflict: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Fetch conflict events with lat/lon for heatmap visualization (ACLED).
    Returns list of { "lat", "lon", "intensity", "source", "event_type", "fatalities" }.
    Intensity is derived from fatalities (capped) and event type (violence = higher).
    """
    cl = conflict.lower()
    acled_country = next(
        (v for k, v in ACLED_COUNTRY_NAMES.items() if k != "default" and k in cl),
        ACLED_COUNTRY_NAMES["default"],
    )
    events: List[Dict[str, Any]] = []
    use_oauth = has_acled_oauth()
    if not use_oauth and not os.getenv("ACLED_API_KEY"):
        return events

    try:
        async def _fetch() -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            token = await get_acled_token_async() if use_oauth else None
            if use_oauth and not token:
                return out
            params = {"_format": "json", "limit": min(500, max(50, limit)), "country": acled_country}
            if token:
                url = ACLED_API_URL
                headers = {"Authorization": f"Bearer {token}"}
            else:
                url = ACLED_LEGACY_URL
                headers = {}
                params["key"] = os.getenv("ACLED_API_KEY", "")
                if os.getenv("ACLED_EMAIL"):
                    params["email"] = os.getenv("ACLED_EMAIL", "")
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    return out
                data = resp.json()
                for rec in (data.get("data") or [])[:limit]:
                    if not isinstance(rec, dict):
                        continue
                    lat_val = rec.get("latitude")
                    lon_val = rec.get("longitude")
                    if lat_val is None or lon_val is None:
                        continue
                    try:
                        lat = float(lat_val)
                        lon = float(lon_val)
                    except (TypeError, ValueError):
                        continue
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                    fatalities = 0
                    try:
                        f = rec.get("fatalities")
                        if f is not None:
                            fatalities = int(f) if isinstance(f, (int, float)) else int(float(str(f).strip() or 0))
                    except (ValueError, TypeError):
                        pass
                    event_type = (rec.get("event_type") or rec.get("sub_event_type") or "")[:80]
                    # Intensity 0–1: base 0.3 + fatalities cap 0.5 + violence types
                    intensity = 0.3
                    if fatalities > 0:
                        intensity = min(0.95, intensity + min(fatalities / 50, 0.5))
                    if any(
                        x in (event_type or "").lower()
                        for x in ("battle", "violence", "explosion", "attack", "armed", "riot")
                    ):
                        intensity = min(0.95, intensity + 0.2)
                    out.append({
                        "lat": round(lat, 5),
                        "lon": round(lon, 5),
                        "intensity": round(intensity, 2),
                        "source": "ACLED",
                        "event_type": event_type or None,
                        "fatalities": fatalities,
                    })
            return out

        events = asyncio.run(_fetch())
    except Exception:
        pass
    return events


# ── Theater Map: unified events for map visualization (Iran / conflict region) ─────
# event_type for frontend: airstrike | missile | drone | explosion | naval | fire | other

def _normalize_theater_event_type(source: str, raw_type: str | None, sub_type: str | None = None) -> str:
    """Map source-specific event type to theater event_type for map icons."""
    if not raw_type:
        return "other"
    t = (raw_type or "").lower()
    if source == "FIRMS":
        if "explosion" in t or t == "explosion":
            return "airstrike"
        if "fire" in t:
            return "fire"
        return "explosion"
    if source == "ACLED":
        if "air" in t and ("strike" in t or "attack" in t):
            return "airstrike"
        if "explosion" in t or "remote violence" in t or "shelling" in t:
            return "explosion"
        if "missile" in t or "rocket" in t:
            return "missile"
        if "drone" in t:
            return "drone"
        if "naval" in t or "sea" in t:
            return "naval"
        if "battle" in t or "armed" in t:
            return "explosion"
        return "other"
    if source == "UCDP":
        return "airstrike"  # UCDP events with coords are conflict events
    return "other"


def get_theater_events(conflict: str, limit: int = 400) -> List[Dict[str, Any]]:
    """
    Unified events for Theater Map: FIRMS thermal anomalies + ACLED + UCDP (with lat/lon).
    Returns list of { lat, lon, event_type, source, confidence?, label? }.
    event_type: airstrike | missile | drone | explosion | naval | fire | other.
    Skips FIRMS industrial/gas-flaring points. Use for Iran (or other conflict) map layer.
    """
    region = get_conflict_region(conflict)
    out: List[Dict[str, Any]] = []

    # 1) FIRMS thermal anomalies (excluding gas flaring)
    try:
        raw_firms = get_thermal_anomalies(region=region, days=3)
        for a in raw_firms if isinstance(raw_firms, list) else []:
            if not isinstance(a, dict) or a.get("error") or a.get("gas_flaring"):
                continue
            lat = _safe_float(a.get("lat"), 0)
            lon = _safe_float(a.get("lon"), 0)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            out.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "event_type": _normalize_theater_event_type("FIRMS", a.get("type")),
                "source": "FIRMS",
                "confidence": a.get("confidence", "nominal"),
                "label": f"FRP {int(_safe_float(a.get('frp'), 0))} MW",
            })
    except Exception:
        pass

    # 2) ACLED events
    try:
        acled = get_conflict_events_for_heatmap(conflict, limit=max(100, min(500, limit)))
        for e in acled:
            if not isinstance(e, dict):
                continue
            lat = _safe_float(e.get("lat"), 0)
            lon = _safe_float(e.get("lon"), 0)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            event_type = _normalize_theater_event_type("ACLED", e.get("event_type"))
            out.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "event_type": event_type,
                "source": "ACLED",
                "confidence": "high" if (e.get("fatalities") or 0) > 0 else "nominal",
                "label": (e.get("event_type") or "Event")[:60],
            })
    except Exception:
        pass

    # 3) UCDP events with coordinates
    try:
        ucdp = get_ucdp_events(conflict)
        for e in ucdp if isinstance(ucdp, list) else []:
            if not isinstance(e, dict):
                continue
            lat_val, lon_val = e.get("latitude"), e.get("longitude")
            if lat_val is None or lon_val is None:
                continue
            try:
                lat = float(lat_val)
                lon = float(lon_val)
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            out.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "event_type": _normalize_theater_event_type("UCDP", e.get("type_of_violence")),
                "source": "UCDP",
                "confidence": "high",
                "label": (e.get("side_a") or "") + " vs " + (e.get("side_b") or ""),
            })
    except Exception:
        pass

    return out[: limit]


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
# Authenticated access: 5,000 requests/day (resets midnight UTC). One paginated request = one count.
UCDP_BASE = "https://ucdpapi.pcr.uu.se/api"
UCDP_GED_VERSION = "25.1"
UCDP_COUNTRY_IDS = {
    "iran": [630],  # Iran (GW)
    "iraq": [645], "syria": [652], "yemen": [679], "israel": [666], "gaza": [667],
    "ukraine": [369], "russia": [365], "libya": [620], "sudan": [625], "afghanistan": [700],
    "default": [630],
}


def get_ucdp_events(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent conflict events from UCDP GED (Uppsala Conflict Data Program).
    API: ucdpapi.pcr.uu.se/api/gedevents/25.1. Requires UCDP_API_TOKEN (x-ucdp-access-token).
    Returns events for the conflict country (e.g. Iran=630); optional StartDate/EndDate for last 90 days.
    """
    token = (os.getenv("UCDP_API_TOKEN") or os.getenv("UCDP_ACCESS_TOKEN") or "").strip()
    if not token:
        return []
    # One request per analysis; stay under 5,000/day (UCDP limit)

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
    # Default (Sentinel-2 / optical) view
    url_s2 = f"{base}/?lat={lat}&lng={lon}&zoom={zoom}"
    # Sentinel-1 SAR (AWD-style radar visualisation) – useful under heavy cloud cover
    url_s1 = (
        f"{base}/?lat={lat}&lng={lon}&zoom={zoom}"
        "&datasetId=S1GRD&fromTime=NOW-7DAYS&toTime=NOW"
        "&layerId=S1-IW-VVVH"
    )
    return {
        "region": region,
        "eo_browser_s2_url": url_s2,
        "eo_browser_s1_sar_url": url_s1,
        "description": "Open in EO Browser for Sentinel-2 (optical) and Sentinel-1 SAR (cloud-penetrating) imagery. Sentinel Hub Process API can be enabled with SENTINELHUB_CLIENT_ID and SENTINELHUB_CLIENT_SECRET.",
    }


# ── Agent ──────────────────────────────────────────────────────────────────

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
    # Ignore gas flares / industrial sites for scoring – they tend to be persistent and not conflict-driven.
    non_flaring = [a for a in anomalies if not a.get("gas_flaring")]
    high = sum(1 for a in non_flaring if a.get("confidence") == "high")
    explosion_count = sum(
        1
        for a in non_flaring
        if a.get("type") == "explosion" or _safe_float(a.get("frp"), 0) > 500
    )
    # Spatial + temporal cluster (radius 0.5°, ≤2h window) for concerted strikes
    clusters = _is_explosion_cluster(non_flaring, radius_deg=0.5, max_hours=2.0)
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
        region = get_conflict_region(conflict=conflict)
        if not isinstance(region, str):
            region = "middle_east"
        raw = get_thermal_anomalies(region=region, days=3)
        anomalies = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]
        reliefweb_raw = get_conflict_hotspot_news(conflict=conflict)
        reliefweb_reports = [r for r in (reliefweb_raw if isinstance(reliefweb_raw, list) else []) if isinstance(r, dict) and "error" not in r]
        has_acled_cfg = has_acled_oauth() or os.getenv("ACLED_API_KEY")
        has_acled_reports = any(r.get("source") == "ACLED" for r in reliefweb_reports)
        ucdp_raw = get_ucdp_events(conflict=conflict)
        ucdp_events = [e for e in (ucdp_raw if isinstance(ucdp_raw, list) else []) if isinstance(e, dict) and "error" not in e]
        eo_links = get_eo_browser_links(conflict=conflict)
        if not isinstance(eo_links, dict):
            eo_links = {}
        score, explosion_count, clusters, _ = _compute_geoint_score(anomalies)
        if ucdp_events:
            score = min(100.0, score + min(15, len(ucdp_events) * 2))
        high = sum(1 for a in anomalies if a.get("confidence") == "high")
        hotspots = sorted(anomalies, key=lambda x: _safe_float(x.get("frp"), 0), reverse=True)[:5]
        summary_extra = f" {len(ucdp_events)} UCDP events." if ucdp_events else ""
        if has_acled_cfg and not has_acled_reports:
            summary_extra += " ACLED data unavailable or empty; score based mainly on thermal anomalies and UCDP/ReliefWeb."
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

    TOOL_FNS = {
        "get_conflict_region": get_conflict_region,
        "get_thermal_anomalies": get_thermal_anomalies,
        "get_conflict_hotspot_news": get_conflict_hotspot_news,
        "get_ucdp_events": get_ucdp_events,
        "get_eo_browser_links": get_eo_browser_links,
    }
    TOOL_SCHEMAS = [
        {"name": "get_conflict_region", "description": "Map conflict to a geographic region.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_thermal_anomalies", "description": "Fetch NASA FIRMS thermal anomalies.", "input_schema": {"type": "object", "properties": {"region": {"type": "string"}, "days": {"type": "integer"}}, "required": ["region"]}},
        {"name": "get_conflict_hotspot_news", "description": "Fetch ReliefWeb/ACLED hotspot news.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_ucdp_events", "description": "Fetch UCDP conflict events.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_eo_browser_links", "description": "Generate EO Browser links.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    ]
    text = run_tool_agent(
        system=GEOINT_SYSTEM,
        user_content=f"Detect thermal anomalies for conflict: {conflict}",
        tool_fns=TOOL_FNS,
        tool_schemas=TOOL_SCHEMAS,
        max_rounds=6,
    )
    if text:
        text = text.strip()
        for prefix in ("```json", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        try:
            result = json.loads(text)
            result["conflict"] = conflict
            return result
        except Exception:
            pass
    return _run_rule_based_geoint(conflict)
