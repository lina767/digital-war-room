"""
GEOINT Agent.
Detects thermal anomalies via NASA FIRMS in conflict regions.
Uses area-specific API (no world download). Supplemented by ReliefWeb/ACLED event data.
"""

import asyncio
import csv
import io
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .context import AgentContext

import httpx

from services.acled_auth import get_acled_token_async, has_acled_oauth

from ..config import RELIEFWEB_APPNAME
from ..utils import run_async, safe_float

logger = logging.getLogger(__name__)

# Format: /api/area/csv/{key}/{source}/{area}/{days} — area = "W,S,E,N" (lon_min, lat_min, lon_max, lat_max)
FIRMS_AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{area}/{days}"

# GDELT DOC 2.0 API – replaces the retired GEO 2.0 endpoint (/api/v2/geo/geo → 404 since late 2025).
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

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

# GDACS (Global Disaster Alert and Coordination System) – earthquakes, cyclones, floods, etc. Optional; uses gdacs-api.
GDACS_EVENT_TYPE_LABEL = {
    "TC": "Tropical Cyclone",
    "EQ": "Earthquake",
    "FL": "Flood",
    "VO": "Volcano",
    "WF": "Wildfire",
    "DR": "Drought",
}
GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


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
    """Local wrapper: geoint always wants a non-None float default."""
    result = safe_float(v)
    return result if result is not None else default


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
                b
                for b in anomalies
                if not b.get("gas_flaring")
                and abs(_safe_float(b.get("lat"), 0) - lat) <= radius_deg
                and abs(_safe_float(b.get("lon"), 0) - lon) <= radius_deg
            ]
        if len(nearby) >= 3:
            used.add(key)
            clusters.append(
                {
                    "center_lat": round(lat, 4),
                    "center_lon": round(lon, 4),
                    "count": len(nearby),
                }
            )
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
        "lat": lat,
        "lon": lon,
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
        all_anomalies = run_async(_fetch_all())
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


def _fetch_thermal_anomalies_for_focus_regions(
    focus_regions: List[Dict[str, Any]], days: int = 3
) -> List[Dict[str, Any]]:
    """Fetch FIRMS thermal anomalies for a bbox around handoff focus regions (SIGINT-derived)."""
    if not focus_regions:
        return []
    api_key = os.getenv("NASA_FIRMS_KEY")
    if not api_key:
        return []
    lats = [float(r["lat"]) for r in focus_regions if isinstance(r, dict) and r.get("lat") is not None]
    lons = [float(r["lon"]) for r in focus_regions if isinstance(r, dict) and r.get("lon") is not None]
    if not lats or not lons:
        return []
    pad = 1.0
    lat_min, lat_max = min(lats) - pad, max(lats) + pad
    lon_min, lon_max = min(lons) - pad, max(lons) + pad
    # FIRMS area format: W,S,E,N = lon_min, lat_min, lon_max, lat_max
    bbox_str = f"{lon_min:.2f},{lat_min:.2f},{lon_max:.2f},{lat_max:.2f}"
    bbox = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max}
    url = FIRMS_AREA_URL.format(key=api_key, area=bbox_str, days=max(1, min(5, days)))

    async def _fetch() -> List[Dict[str, Any]]:
        out = []
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            for row in csv.DictReader(io.StringIO(resp.text)):
                a = _parse_firms_row(row, bbox)
                if a:
                    out.append(a)
        return out

    try:
        return run_async(_fetch())
    except Exception:
        return []


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


def _get_gdacs_events_for_region(region: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch latest disaster events from GDACS (gdacs-api) and filter by region bbox.
    Returns report-like dicts (title, date, body_excerpt, source, country) for merging with hotspot news.
    """
    def _raw_features() -> List[Dict[str, Any]]:
        """
        Get GDACS features either via gdacs-api package or direct public API fallback.
        This keeps GEOINT working even if gdacs-api is not installed in runtime.
        """
        try:
            from gdacs.api import GDACSAPIReader

            client = GDACSAPIReader()
            result = client.latest_events(limit=limit)
            features = getattr(result, "features", None)
            if features is None and isinstance(result, dict):
                features = result.get("features", [])
            if isinstance(features, list):
                return [f for f in features if isinstance(f, dict)]
        except ImportError:
            logger.info("GDACS: gdacs-api not installed; using direct API fallback.")
        except Exception as e:
            logger.debug("GDACS: gdacs-api reader failed, using fallback: %s", e)

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(GDACS_EVENTS_URL)
                resp.raise_for_status()
                data = resp.json()
            features = data.get("features", []) if isinstance(data, dict) else []
            if isinstance(features, list):
                return [f for f in features if isinstance(f, dict)]
        except Exception as e:
            logger.debug("GDACS direct API fallback failed: %s", e)
        return []

    areas_to_filter = SUB_REGIONS_FOR_REGION.get(region, [region])
    bboxes: List[Dict[str, float]] = []
    for area in areas_to_filter:
        bbox_str = REGION_BBOX.get(area)
        if bbox_str:
            bboxes.append(_bbox_to_region(bbox_str))
    if not bboxes:
        bboxes = [_bbox_to_region(REGION_BBOX["middle_east"])]

    def _in_any_bbox(lat: float, lon: float) -> bool:
        for b in bboxes:
            if b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]:
                return True
        return False

    reports: List[Dict[str, Any]] = []
    seen: set[str] = set()
    try:
        features = _raw_features()
        if not isinstance(features, list):
            return []
        for f in features:
            if not isinstance(f, dict):
                continue
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") if isinstance(geom, dict) else None
            if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            if not _in_any_bbox(lat, lon):
                continue
            props = f.get("properties") or {}
            event_type = (props.get("eventtype") or "").strip().upper()
            label = GDACS_EVENT_TYPE_LABEL.get(event_type, event_type or "Disaster")
            name = (props.get("name") or props.get("title") or label).strip()[:200]
            from_date = props.get("fromdate") or props.get("pubdate") or props.get("date") or ""
            alert_level = (props.get("alertlevel") or "").strip()
            title = f"{label}: {name}" if name != label else f"{label} ({alert_level})".strip(" ()") or label
            dedupe_key = f"{title}|{str(from_date)[:30]}|{round(lat, 2)}|{round(lon, 2)}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            reports.append(
                {
                    "title": title[:300],
                    "date": str(from_date)[:30],
                    "body_excerpt": f"Alert: {alert_level}" if alert_level else f"Location: {lat:.2f}, {lon:.2f}",
                    "source": "GDACS",
                    "country": props.get("country") or props.get("location") or region,
                }
            )
    except Exception as e:
        logger.debug("GDACS fetch failed: %s", e)
    return reports[: min(15, max(1, int(limit)))]


# HDX HAPI (https://hapi.humdata.org/docs) – humanitarian indicators by country (ISO3). Optional HAPI_APP_IDENTIFIER.
HAPI_BASE_URL = "https://hapi.humdata.org/api/v1"
HAPI_APP_IDENTIFIER = (os.getenv("HAPI_APP_IDENTIFIER") or "").strip()
# Conflict key -> list of ISO3 codes for HAPI location_code filter
HAPI_ISO3_BY_CONFLICT: Dict[str, List[str]] = {
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

# ReliefWeb API v2: filter by country name (e.g. "Iran", "Ukraine"). appname from config.
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


async def _fetch_hapi_reports(iso3_codes: List[str], client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Fetch humanitarian data from HDX HAPI (operational presence + conflict events).
    Returns report-like dicts (title, date, body_excerpt, source, country) for merging with ReliefWeb.
    Requires HAPI_APP_IDENTIFIER in env (generate at https://hapi.humdata.org/docs).
    """
    if not HAPI_APP_IDENTIFIER or not iso3_codes:
        return []
    reports: List[Dict[str, Any]] = []
    params_base = {"output_format": "json", "limit": 100, "app_identifier": HAPI_APP_IDENTIFIER}

    for theme, normalize in [
        ("coordination-context/operational-presence", _normalize_hapi_operational_presence),
        ("coordination-context/conflict-events", _normalize_hapi_conflict_events),
    ]:
        for iso3 in iso3_codes[:3]:
            try:
                url = f"{HAPI_BASE_URL}/{theme}"
                params = {**params_base, "location_code": iso3.upper()}
                resp = await client.get(url, params=params, timeout=12.0)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("data", data.get("results", []))
                if not isinstance(rows, list):
                    continue
                for row in rows[:15]:
                    if isinstance(row, dict):
                        item = normalize(row)
                        if item:
                            reports.append(item)
            except Exception as e:
                logger.debug("GEOINT HAPI %s for %s failed: %s", theme, iso3, e)
    return reports[:20]


def _normalize_hapi_operational_presence(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn HAPI operational-presence row into report-like dict."""
    org = (row.get("org_name") or row.get("org_acronym") or "").strip()
    sector = (row.get("sector_name") or "").strip()
    loc = (row.get("location_name") or "").strip()
    if not loc:
        return None
    title = f"{org} – {sector}" if org and sector else (org or sector or "Operational presence")
    ref_end = row.get("reference_period_end") or row.get("reference_period_start") or ""
    admin1 = (row.get("admin1_name") or "").strip()
    admin2 = (row.get("admin2_name") or "").strip()
    body = " ".join(filter(None, [admin1, admin2])).strip()
    return {
        "title": (title or "Operational presence")[:300],
        "date": str(ref_end)[:30],
        "body_excerpt": body[:200] if body else f"Location: {loc}",
        "source": "HDX HAPI",
        "country": loc,
    }


def _normalize_hapi_conflict_events(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn HAPI conflict-events row into report-like dict."""
    loc = (row.get("location_name") or "").strip()
    if not loc:
        return None
    event_type = (row.get("event_type") or "Conflict events").strip()
    events = row.get("events")
    fatalities = row.get("fatalities")
    parts = [event_type]
    if events is not None:
        parts.append(f"{int(events)} events")
    if fatalities is not None:
        parts.append(f"{int(fatalities)} fatalities")
    title = " – ".join(parts)
    ref_end = row.get("reference_period_end") or row.get("reference_period_start") or ""
    admin1 = (row.get("admin1_name") or "").strip()
    return {
        "title": title[:300],
        "date": str(ref_end)[:30],
        "body_excerpt": (admin1 or loc)[:200],
        "source": "HDX HAPI (ACLED)",
        "country": loc,
    }


async def _reliefweb_rss_fallback(countries: list) -> List[Dict[str, Any]]:
    """Fallback: scrape ReliefWeb RSS feed when API returns 403 (appname not approved)."""

    try:
        import feedparser
    except ImportError:
        return []
    reports: List[Dict[str, Any]] = []
    country_kw = [c.lower() for c in countries]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://reliefweb.int/updates/rss.xml", follow_redirects=True)
            if resp.status_code != 200:
                return []
            feed = feedparser.parse(resp.text)
            for entry in (getattr(feed, "entries", None) or [])[:40]:
                title = (entry.get("title") or "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary") or entry.get("description") or "")[:200]
                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in country_kw):
                    continue
                reports.append(
                    {
                        "title": title[:300],
                        "date": entry.get("published") or "",
                        "body_excerpt": summary,
                        "source": "ReliefWeb (RSS)",
                        "country": next(
                            (c for c in countries if c.lower() in combined), countries[0] if countries else ""
                        ),
                    }
                )
                if len(reports) >= 10:
                    break
    except Exception as e:
        logger.debug("ReliefWeb RSS fallback failed: %s", e)
    return reports


def get_conflict_hotspot_news(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch recent geospatial event reports from ReliefWeb API v2 and optionally ACLED.
    ReliefWeb: filter by country name; falls back to RSS if API returns 403.
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
        last_rw_error = None
        use_rss_fallback = False
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
                    if resp.status_code == 403:
                        last_rw_error = "HTTP 403 – appname not approved. Register at https://apidoc.reliefweb.int/parameters#appname"
                        use_rss_fallback = True
                        break
                    if resp.status_code != 200:
                        last_rw_error = f"HTTP {resp.status_code}"
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
                    country_display = (
                        country_list[0].get("name", country_name)
                        if country_list and isinstance(country_list[0], dict)
                        else country_name
                    )
                    reports.append(
                        {
                            "title": title,
                            "date": date_created,
                            "body_excerpt": body_excerpt,
                            "source": source,
                            "country": country_display,
                        }
                    )
            except Exception as e:
                last_rw_error = str(e)
                continue

        if use_rss_fallback and not reports:
            reports = await _reliefweb_rss_fallback(rw_countries)

        if not reports and last_rw_error:
            logger.warning(
                "ReliefWeb/ACLED: ReliefWeb request failed (%s). Check RELIEFWEB_APPNAME or register at https://apidoc.reliefweb.int/parameters#appname.",
                last_rw_error,
            )
        elif not reports:
            logger.info(
                "ReliefWeb/ACLED: ReliefWeb returned no reports for countries %s (empty is normal for some regions).",
                rw_countries[:3],
            )
        return reports[:15]

    try:
        reports = run_async(_reliefweb())
    except Exception as e:
        logger.warning("ReliefWeb/ACLED: ReliefWeb fetch failed: %s. Check network and api.reliefweb.int.", e)
        reports = [{"error": str(e)}]

    # Keep ACLED/GDACS/HAPI independent from ReliefWeb transient failures.
    if isinstance(reports, list) and any(isinstance(r, dict) and r.get("error") for r in reports):
        logger.info("ReliefWeb/ACLED: ReliefWeb returned errors; continuing with ACLED/GDACS/HAPI sources.")
        reports = []

    # GDACS: disaster events (earthquakes, cyclones, floods, etc.) in conflict region
    if isinstance(reports, list):
        try:
            region = get_conflict_region(conflict)
            gdacs_items = _get_gdacs_events_for_region(region)
            if gdacs_items:
                reports.extend(gdacs_items)
        except Exception as e:
            logger.debug("GEOINT GDACS fetch failed: %s", e)

    # HDX HAPI: merge humanitarian indicators (operational presence, conflict events) when app identifier is set
    if (
        HAPI_APP_IDENTIFIER
        and isinstance(reports, list)
    ):
        try:
            iso3_list = next(
                (v for k, v in HAPI_ISO3_BY_CONFLICT.items() if k != "default" and k in cl),
                HAPI_ISO3_BY_CONFLICT["default"],
            )

            async def _hapi():
                async with httpx.AsyncClient(timeout=14.0) as client:
                    return await _fetch_hapi_reports(iso3_list, client)

            hapi_items = run_async(_hapi())
            if hapi_items:
                reports.extend(hapi_items)
        except Exception as e:
            logger.debug("GEOINT HDX HAPI fetch failed: %s", e)

    acled_ok = has_acled_oauth() or os.getenv("ACLED_API_KEY")
    if acled_ok and isinstance(reports, list):
        try:

            async def _acled():
                token = await get_acled_token_async() if has_acled_oauth() else None
                if has_acled_oauth() and not token:
                    logger.debug(
                        "ReliefWeb/ACLED: ACLED skipped (OAuth token missing). Set ACLED_EMAIL/ACLED_PASSWORD."
                    )
                    return

                if token:
                    url = ACLED_API_URL
                    headers = {"Authorization": f"Bearer {token}"}
                else:
                    url = ACLED_LEGACY_URL
                    headers = {}
                async with httpx.AsyncClient(timeout=14.0) as client:
                    # ACLED research tier may be delayed; fall back from 90d to 540d.
                    got_items = False
                    for days in (90, 540):
                        event_date_val, event_date_where = _acled_event_date_range(days)
                        params = {
                            "_format": "json",
                            "limit": 10,
                            "country": acled_country,
                            "event_date": event_date_val,
                            "event_date_where": event_date_where,
                        }
                        if not token:
                            params["key"] = os.getenv("ACLED_API_KEY", "")
                            if os.getenv("ACLED_EMAIL"):
                                params["email"] = os.getenv("ACLED_EMAIL", "")
                        resp = await client.get(url, params=params, headers=headers)
                        if resp.status_code != 200:
                            logger.warning(
                                "ReliefWeb/ACLED: ACLED API returned HTTP %s for country=%s (range=%sd). OAuth/credentials see acled_auth logs.",
                                resp.status_code,
                                acled_country,
                                days,
                            )
                            return
                        data = resp.json()
                        rows = data.get("data") or []
                        for rec in rows[:10]:
                            if isinstance(rec, dict):
                                reports.append(
                                    {
                                        "title": (rec.get("event") or rec.get("title") or "")[:300],
                                        "date": rec.get("event_date", ""),
                                        "body_excerpt": (rec.get("notes") or "")[:200],
                                        "source": "ACLED",
                                        "country": rec.get("country", acled_country),
                                    }
                                )
                        if rows:
                            got_items = True
                            break
                    if not got_items:
                        logger.info(
                            "ReliefWeb/ACLED: ACLED returned no rows for %s in 90d and 540d windows.",
                            acled_country,
                        )

            run_async(_acled())
        except Exception as e:
            logger.warning("ReliefWeb/ACLED: ACLED request failed: %s", e)
    elif not acled_ok and not reports:
        logger.info(
            "ReliefWeb/ACLED: No data. ReliefWeb returned empty and ACLED credentials not set (ACLED_EMAIL + ACLED_PASSWORD in backend/.env)."
        )
    return reports if isinstance(reports, list) else [{"error": "unknown"}]


def _acled_event_date_range(days: int = 90) -> Tuple[str, str]:
    """Return (event_date_value, event_date_where) for ACLED API (last N days)."""
    end_d = datetime.now(timezone.utc)
    start_d = end_d - timedelta(days=days)
    return f"{start_d.strftime('%Y-%m-%d')}|{end_d.strftime('%Y-%m-%d')}", "BETWEEN"


def get_conflict_events_for_heatmap(conflict: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Fetch conflict events with lat/lon for heatmap visualization (ACLED).
    Returns list of { "lat", "lon", "intensity", "source", "event_type", "fatalities" }.
    Intensity is derived from fatalities (capped) and event type (violence = higher).
    Requests last 90 days via event_date + event_date_where=BETWEEN (ACLED API reference).
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
        event_date_val, event_date_where = _acled_event_date_range(90)

        async def _fetch() -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            token = await get_acled_token_async() if use_oauth else None
            if use_oauth and not token:
                return out
            if token:
                url = ACLED_API_URL
                headers = {"Authorization": f"Bearer {token}"}
            else:
                url = ACLED_LEGACY_URL
                headers = {}
            async with httpx.AsyncClient(timeout=20.0) as client:
                got_rows = False
                for days in (90, 540):
                    event_date_val, event_date_where = _acled_event_date_range(days)
                    params = {
                        "_format": "json",
                        "limit": min(500, max(50, limit)),
                        "country": acled_country,
                        "event_date": event_date_val,
                        "event_date_where": event_date_where,
                    }
                    if not token:
                        params["key"] = os.getenv("ACLED_API_KEY", "")
                        if os.getenv("ACLED_EMAIL"):
                            params["email"] = os.getenv("ACLED_EMAIL", "")
                    resp = await client.get(url, params=params, headers=headers)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    rows = data.get("data") or []
                    for rec in rows[:limit]:
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
                        intensity = 0.3
                        if fatalities > 0:
                            intensity = min(0.95, intensity + min(fatalities / 50, 0.5))
                        if any(
                            x in (event_type or "").lower()
                            for x in ("battle", "violence", "explosion", "attack", "armed", "riot")
                        ):
                            intensity = min(0.95, intensity + 0.2)
                        actor1 = (rec.get("actor1") or "").strip() or None
                        actor2 = (rec.get("actor2") or "").strip() or None
                        notes = (rec.get("notes") or "").strip() or None
                        if notes and len(notes) > 500:
                            notes = notes[:497] + "..."
                        event_date = (rec.get("event_date") or rec.get("date") or "").strip() or None
                        sub_event_type = (rec.get("sub_event_type") or "").strip() or None
                        out.append(
                            {
                                "lat": round(lat, 5),
                                "lon": round(lon, 5),
                                "intensity": round(intensity, 2),
                                "source": "ACLED",
                                "event_type": event_type or None,
                                "fatalities": fatalities,
                                "actor1": actor1,
                                "actor2": actor2,
                                "notes": notes,
                                "event_date": event_date,
                                "sub_event_type": sub_event_type,
                            }
                        )
                    if rows:
                        got_rows = True
                        break
                if not got_rows:
                    logger.info("GEOINT heatmap ACLED: no rows for %s in 90d and 540d windows.", acled_country)
            return out

        events = run_async(_fetch())
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
    st = (sub_type or "").lower()
    if source == "FIRMS":
        # FIRMS _classify(): explosion | fire | unknown (not ACLED text — do not map explosion → airstrike).
        if t == "fire" or ("fire" in t and "explosion" not in t):
            return "fire"
        if t == "explosion" or "explosion" in t:
            return "explosion"
        return "other"
    if source == "ACLED":
        if "air" in st or "drone" in st:
            return "airstrike"
        if "shelling" in st or "missile" in st or "artillery" in st:
            return "missile"
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
    return "other"


MILITARY_EVENT_TYPES = {
    "Battles",
    "Explosions/Remote violence",
    "Violence against civilians",
}
MILITARY_SUB_EVENTS_THEATER = {
    "Air/drone strike": "airstrike",
    "Shelling/artillery/missile attack": "missile",
    "Armed clash": "explosion",
    "Remote explosive/landmine/IED": "explosion",
    "Suicide bomb": "explosion",
    "Grenade": "explosion",
    "Attack": "explosion",
    "Abduction/forced disappearance": "other",
    "Sexual violence": "other",
}
ACLED_AGGREGATED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "acled")


def _load_aggregated_theater_events(conflict: str, weeks: int = 4) -> List[Dict[str, Any]]:
    """Load recent military events from aggregated CSVs for theater map display.
    Returns list of dicts with lat, lon, event_type, etc."""
    cl = conflict.lower()
    country_files = []
    if "iran" in cl:
        country_files.extend(
            [
                ("Iran", "acled_iran_aggregated_current.csv"),
                ("Israel", "acled_israel_aggregated_current.csv"),
                ("Iraq", "acled_iraq_aggregated_current.csv"),
                ("Syria", "acled_syria_aggregated_current.csv"),
                ("Lebanon", "acled_lebanon_aggregated_current.csv"),
                ("Yemen", "acled_yemen_aggregated_current.csv"),
            ]
        )
    elif "israel" in cl or "gaza" in cl:
        country_files.extend(
            [
                ("Israel", "acled_israel_aggregated_current.csv"),
                ("Palestine", "acled_palestine_aggregated_current.csv"),
                ("Lebanon", "acled_lebanon_aggregated_current.csv"),
                ("Iran", "acled_iran_aggregated_current.csv"),
            ]
        )
    elif "ukraine" in cl:
        return []
    else:
        country_files.append(("Iran", "acled_iran_aggregated_current.csv"))

    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    events: List[Dict[str, Any]] = []

    for country, fname in country_files:
        fpath = os.path.join(ACLED_AGGREGATED_DIR, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("week", "") < cutoff:
                        continue
                    if row.get("event_type") not in MILITARY_EVENT_TYPES:
                        continue
                    sub = row.get("sub_event_type", "")
                    if sub in ("Peaceful protest", "Protest with intervention", "Excessive force against protesters"):
                        continue
                    lat = _safe_float(row.get("centroid_lat"), 0)
                    lon = _safe_float(row.get("centroid_lon"), 0)
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                        continue
                    ev_count = int(row.get("events") or 0)
                    fatalities = int(row.get("fatalities") or 0)
                    if ev_count == 0:
                        continue
                    theater_type = MILITARY_SUB_EVENTS_THEATER.get(sub, "other")
                    label = f"{sub} · {ev_count} events"
                    if fatalities > 0:
                        label += f", {fatalities} fatalities"
                    label += f" ({row.get('admin1', '?')}, {country})"
                    events.append(
                        {
                            "lat": round(lat, 5),
                            "lon": round(lon, 5),
                            "event_type": theater_type,
                            "source": "ACLED-Aggregated",
                            "confidence": "high" if fatalities > 0 else "nominal",
                            "label": label,
                            "event_date": row.get("week"),
                            "sub_event_type": sub,
                            "fatalities": fatalities,
                            "events_count": ev_count,
                            "country": country,
                            "admin1": row.get("admin1", ""),
                        }
                    )
        except Exception as e:
            logger.warning("Failed to load aggregated theater data from %s: %s", fname, e)

    return events


def get_theater_events(conflict: str, limit: int = 400) -> List[Dict[str, Any]]:
    """
    Unified events for Theater Map: aggregated ACLED (real-time) + FIRMS + ACLED API.
    Returns list of { lat, lon, event_type, source, confidence?, label? }.
    event_type: airstrike | missile | drone | explosion | naval | fire | other.
    Skips FIRMS industrial/gas-flaring points. Use for Iran (or other conflict) map layer.
    """
    region = get_conflict_region(conflict)
    out: List[Dict[str, Any]] = []

    # 1) Aggregated ACLED data (real-time weekly, military events across the region)
    try:
        from services.acled_aggregated import refresh_acled_aggregated

        refresh_acled_aggregated()
    except Exception:
        pass
    try:
        agg_events = _load_aggregated_theater_events(conflict, weeks=4)
        out.extend(agg_events)
        if agg_events:
            logger.info("Theater: %d aggregated military events loaded for %s", len(agg_events), conflict)
    except Exception as e:
        logger.warning("Theater: aggregated load failed: %s", e)

    # 2) FIRMS thermal anomalies (excluding gas flaring)
    try:
        raw_firms = get_thermal_anomalies(region=region, days=3)
        for a in raw_firms if isinstance(raw_firms, list) else []:
            if not isinstance(a, dict) or a.get("error") or a.get("gas_flaring"):
                continue
            lat = _safe_float(a.get("lat"), 0)
            lon = _safe_float(a.get("lon"), 0)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            frp = int(_safe_float(a.get("frp"), 0))
            eo_url = f"https://apps.sentinel-hub.com/eo-browser/?lat={lat}&lng={lon}&zoom=10"
            out.append(
                {
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "event_type": _normalize_theater_event_type("FIRMS", a.get("type")),
                    "source": "FIRMS",
                    "confidence": a.get("confidence", "nominal"),
                    "label": f"FRP {frp} MW (thermal anomaly – satellite)",
                    "url": eo_url,
                    "event_date": a.get("acquired"),
                }
            )
    except Exception:
        pass

    # 3) ACLED API events (historical, ~12-month lag on Research level)
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
            label = (e.get("event_type") or "Event")[:60]
            if e.get("fatalities"):
                label = f"{label} · {e.get('fatalities')} fatality/fatalities"
            evt = {
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "event_type": event_type,
                "source": "ACLED",
                "confidence": "high" if (e.get("fatalities") or 0) > 0 else "nominal",
                "label": label,
            }
            if e.get("fatalities") is not None:
                evt["fatalities"] = int(e["fatalities"])
            for key in ("actor1", "actor2", "notes", "event_date", "sub_event_type"):
                if e.get(key):
                    evt[key] = e[key]
            out.append(evt)
    except Exception:
        pass

    return out[:limit]


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
    url_s1 = f"{base}/?lat={lat}&lng={lon}&zoom={zoom}&datasetId=S1GRD&fromTime=NOW-7DAYS&toTime=NOW&layerId=S1-IW-VVVH"
    return {
        "region": region,
        "eo_browser_s2_url": url_s2,
        "eo_browser_s1_sar_url": url_s1,
        "description": "Open in EO Browser for Sentinel-2 (optical) and Sentinel-1 SAR (cloud-penetrating) imagery. Sentinel Hub Process API can be enabled with SENTINELHUB_CLIENT_ID and SENTINELHUB_CLIENT_SECRET.",
    }


def _gdelt_geo_query(conflict: str) -> str:
    """Build GDELT GEO 2.0 query string from conflict (keyword or OR phrase)."""
    cl = conflict.lower()
    if "iran" in cl or "israel" in cl:
        return "(Iran OR IRGC OR Israel OR Gaza OR Persian Gulf)"
    if "ukraine" in cl or "russia" in cl:
        return "(Ukraine OR Russia OR Donbas OR Kyiv)"
    if "yemen" in cl:
        return "Yemen"
    if "syria" in cl:
        return "Syria"
    if "lebanon" in cl:
        return "Lebanon"
    # Fallback: use conflict as phrase (max one phrase for GEO)
    return conflict.strip()[:100] or "conflict"


def get_gdelt_geo_countries(conflict: str) -> List[Dict[str, Any]]:
    """
    Fetch geo-relevant articles via GDELT DOC API (replaces retired GEO 2.0 endpoint).
    Extracts source-country distribution from article metadata.
    Free, no API key. Returns list of { "country": str, "percent": float }.
    """
    query = _gdelt_geo_query(conflict)

    async def _fetch() -> list:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": 75,
            "timespan": "48H",
        }
        max_retries = 2
        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(GDELT_DOC_URL, params=params)
                if resp.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(6)
                    continue
                ct = (resp.headers.get("content-type") or "").lower()
                if "json" not in ct and "javascript" not in ct:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(6)
                        continue
                    return []
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data.get("articles") or []
                return data if isinstance(data, list) else []
        return []

    try:
        articles = run_async(_fetch())
        if not articles:
            return []
        country_counts: Dict[str, int] = {}
        for art in articles:
            if not isinstance(art, dict):
                continue
            sc = (art.get("sourcecountry") or art.get("domain") or "").strip()
            if sc:
                country_counts[sc] = country_counts.get(sc, 0) + 1
        total = sum(country_counts.values()) or 1
        out: List[Dict[str, Any]] = [
            {"country": c, "percent": round(n / total * 100, 2)} for c, n in country_counts.items()
        ]
        return sorted(out, key=lambda x: x.get("percent", 0), reverse=True)[:30]
    except Exception as e:
        logger.debug("GDELT GEO fetch failed: %s", e)
        return []
