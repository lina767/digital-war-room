"""
Proximity correlation: Overpass (schools/hospitals) + optional tunnel/sites GeoJSON.
Shared by api routes and PROXIMITY agent. Used for IRGC tunnel vs. civilian infrastructure (human shield).

V2 upgrades:
- geometry-aware distance for OSM ways/relations (Shapely with robust fallback),
- semantic event parsing from description (Gemini),
- optional visual verification via Google Static + Gemini vision,
- dynamic risk synthesis while preserving legacy risk labels/fields.
"""

import asyncio
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from services.proximity_semantic_analysis import analyze_event_description
from services.proximity_vision_verification import verify_facility_visual

try:
    from shapely.geometry import LineString, Point, Polygon

    HAS_SHAPELY = True
except Exception:  # pragma: no cover - fallback path tested via behavior
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
RADIUS_M = 300
CRITICAL_M = 50
HIGH_RISK_M = 150
HUMAN_SHIELD_NEAR_M = 100
PROXIMITY_ADVANCED_RISK_ENABLED = (os.getenv("PROXIMITY_ADVANCED_RISK_ENABLED", "1").strip().lower() in ("1", "true", "yes"))
PROXIMITY_SEMANTIC_ENABLED = (os.getenv("PROXIMITY_SEMANTIC_ENABLED", "1").strip().lower() in ("1", "true", "yes"))
PROXIMITY_VISION_ENABLED = (os.getenv("PROXIMITY_VISION_ENABLED", "1").strip().lower() in ("1", "true", "yes"))
PROXIMITY_VISION_MIN_RISK = os.getenv("PROXIMITY_VISION_MIN_RISK", "HIGH_RISK").strip().upper()
# Delay between *batch* Overpass calls when a run needs multiple batches (rate limit courtesy).
OVERPASS_DELAY_S = 1.1
# Cache OSM facility lists per strike location (rounded); default 1 h.
OVERPASS_CACHE_TTL_S = max(60, int(os.getenv("OVERPASS_CACHE_TTL_S", "3600")))
# Max distinct coordinates per single Overpass union query (env cap 1–15).
OVERPASS_BATCH_SIZE = max(1, min(15, int(os.getenv("OVERPASS_BATCH_SIZE", "10"))))

_overpass_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_overpass_cache_lock = asyncio.Lock()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two WGS84 points (Haversine)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cache_key(lat: float, lon: float) -> str:
    """Stable key for OSM cache (≈1 m precision)."""
    return f"{round(lat, 5)},{round(lon, 5)}"


def _overpass_query_batch(coords: List[Tuple[float, float]], radius_m: int) -> str:
    """Single Overpass union query for multiple centers (batch)."""
    lines: List[str] = []
    for lat, lon in coords:
        lines.append(f'  node(around:{radius_m},{lat},{lon})["amenity"~"school|hospital|place_of_worship"];')
        lines.append(f'  way(around:{radius_m},{lat},{lon})["amenity"~"school|hospital|place_of_worship"];')
        lines.append(f'  relation(around:{radius_m},{lat},{lon})["amenity"~"school|hospital|place_of_worship"];')
        lines.append(f'  node(around:{radius_m},{lat},{lon})["office"="government"];')
        lines.append(f'  way(around:{radius_m},{lat},{lon})["office"="government"];')
        lines.append(f'  relation(around:{radius_m},{lat},{lon})["office"="government"];')
    inner = "\n".join(lines)
    return f"""
[out:json][timeout:25];
(
{inner}
);
out body geom center;
""".strip()


def _parse_overpass_elements(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Overpass JSON elements into deduplicated facility dicts."""
    elements = data.get("elements") or []
    facilities: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:en") or "Unnamed facility"
        geometry_points = el.get("geometry") if isinstance(el.get("geometry"), list) else []
        geometry_latlon: List[Tuple[float, float]] = []
        for gp in geometry_points:
            if not isinstance(gp, dict):
                continue
            try:
                geometry_latlon.append((float(gp.get("lat")), float(gp.get("lon"))))
            except Exception:
                continue
        if el.get("type") == "node":
            flat, flon = float(el.get("lat", 0)), float(el.get("lon", 0))
            geometry_type = "point"
        elif el.get("type") == "way" and el.get("center"):
            c = el["center"]
            flat, flon = float(c.get("lat", 0)), float(c.get("lon", 0))
            geometry_type = "polygon_or_line" if geometry_latlon else "point"
        elif el.get("type") == "relation" and el.get("center"):
            c = el["center"]
            flat, flon = float(c.get("lat", 0)), float(c.get("lon", 0))
            geometry_type = "relation"
        else:
            continue
        key = f"{flat:.5f}-{flon:.5f}-{name}"
        if key in seen:
            continue
        seen.add(key)
        facilities.append(
            {
                "id": str(el.get("id", key)),
                "name": name,
                "lat": flat,
                "lon": flon,
                "amenity": tags.get("amenity"),
                "office": tags.get("office"),
                "osm_type": el.get("type"),
                "geometry_type": geometry_type,
                "geometry": geometry_latlon,
            }
        )
    return facilities


def _facilities_within_radius(
    strike_lat: float, strike_lon: float, union_facilities: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Facilities within RADIUS_M of the strike (filters batch union to this point)."""
    if not union_facilities:
        return []
    return [f for f in union_facilities if haversine_m(strike_lat, strike_lon, f["lat"], f["lon"]) <= RADIUS_M]


async def _post_overpass(query: str, _retries: int = 2) -> Optional[Dict[str, Any]]:
    """POST Overpass interpreter; try mirror endpoints on failure."""
    data: Optional[Dict[str, Any]] = None
    for endpoint_url in OVERPASS_URLS:
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        endpoint_url,
                        content=f"data={quote(query)}",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < _retries:
                    wait = OVERPASS_DELAY_S * (attempt + 2)
                    logger.info(
                        "Overpass 429 on %s – retrying in %.1fs (%d/%d)", endpoint_url[:40], wait, attempt + 1, _retries
                    )
                    await asyncio.sleep(wait)
                    attempt += 1
                    continue
                if e.response.status_code == 429:
                    logger.info("Overpass 429 exhausted on %s – trying next endpoint", endpoint_url[:40])
                else:
                    logger.debug("Overpass %s error %s", endpoint_url[:40], e.response.status_code)
                break
            except Exception as e:
                logger.debug("Overpass %s failed: %s", endpoint_url[:40], e)
                break
        if data is not None:
            break
    return data


async def _fetch_and_cache_batch(coords: List[Tuple[float, float]]) -> None:
    """One Overpass round-trip for up to OVERPASS_BATCH_SIZE distinct points; fills TTL cache per point."""
    if not coords:
        return
    query = _overpass_query_batch(coords, RADIUS_M)
    data = await _post_overpass(query)
    expires = time.monotonic() + OVERPASS_CACHE_TTL_S
    if data is None:
        logger.warning("Overpass: batch failed for %d point(s)", len(coords))
        async with _overpass_cache_lock:
            for lat, lon in coords:
                _overpass_cache[_cache_key(lat, lon)] = (expires, [])
        return
    union_facilities = _parse_overpass_elements(data)
    async with _overpass_cache_lock:
        for lat, lon in coords:
            facs = _facilities_within_radius(lat, lon, union_facilities)
            _overpass_cache[_cache_key(lat, lon)] = (expires, facs)


async def fetch_overpass_context(lat: float, lon: float) -> List[Dict[str, Any]]:
    """Return civilian facilities within RADIUS_M of (lat, lon); uses TTL cache and batch POST on miss."""
    key = _cache_key(lat, lon)
    async with _overpass_cache_lock:
        entry = _overpass_cache.get(key)
        if entry and entry[0] > time.monotonic():
            return list(entry[1])
    await _fetch_and_cache_batch([(lat, lon)])
    async with _overpass_cache_lock:
        entry = _overpass_cache.get(key)
        return list(entry[1]) if entry else []


def _tunnel_sites_from_geojson(fc: Dict[str, Any]) -> List[tuple[float, float]]:
    """Extract (lat, lon) from a GeoJSON FeatureCollection (points)."""
    out = []
    for f in fc.get("features") or []:
        geom = f.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        out.append((float(coords[1]), float(coords[0])))  # GeoJSON is [lon, lat]
    return out


def _distance_to_geometry_m(strike_lat: float, strike_lon: float, fac: Dict[str, Any]) -> Tuple[float, str]:
    """Distance in meters to facility geometry; fallback to center Haversine."""
    center_distance = haversine_m(strike_lat, strike_lon, fac["lat"], fac["lon"])
    if not HAS_SHAPELY:
        return center_distance, "haversine_center"
    geometry = fac.get("geometry") or []
    if not isinstance(geometry, list) or len(geometry) < 2:
        return center_distance, "haversine_center"
    coords = []
    for lat, lon in geometry:
        try:
            coords.append((float(lon), float(lat)))
        except Exception:
            continue
    if len(coords) < 2:
        return center_distance, "haversine_center"
    try:
        strike_pt = Point(float(strike_lon), float(strike_lat))
        shape = None
        # Closed ring with enough points => polygon boundary distance.
        if len(coords) >= 4 and coords[0] == coords[-1]:
            shape = Polygon(coords)
        else:
            shape = LineString(coords)
        nearest_pt = shape.exterior.interpolate(shape.exterior.project(strike_pt)) if isinstance(shape, Polygon) else shape.interpolate(shape.project(strike_pt))
        geom_distance = haversine_m(strike_lat, strike_lon, float(nearest_pt.y), float(nearest_pt.x))
        return geom_distance, "shapely_geometry"
    except Exception:
        return center_distance, "haversine_center"


def _nearest_and_risk(
    strike_lat: float,
    strike_lon: float,
    facilities: List[Dict[str, Any]],
    tunnel_points: Optional[List[tuple[float, float]]],
) -> Optional[Dict[str, Any]]:
    """Nearest facility, distance in m, and risk label (CRITICAL_PROXIMITY, HIGH_RISK, PROBABLE_HUMAN_SHIELD, ELEVATED)."""
    if not facilities:
        return None
    best = None
    best_dist = 1e9
    best_distance_method = "haversine_center"
    for fac in facilities:
        d, distance_method = _distance_to_geometry_m(strike_lat, strike_lon, fac)
        if d < best_dist and d <= RADIUS_M:
            best_dist = d
            best = fac
            best_distance_method = distance_method
    if not best:
        return None
    if best_dist < CRITICAL_M:
        risk = "CRITICAL_PROXIMITY"
    elif best_dist < HIGH_RISK_M:
        risk = "HIGH_RISK"
    else:
        risk = "ELEVATED"
    if tunnel_points and risk in ("CRITICAL_PROXIMITY", "HIGH_RISK", "ELEVATED"):
        for tlat, tlon in tunnel_points:
            if haversine_m(best["lat"], best["lon"], tlat, tlon) < HUMAN_SHIELD_NEAR_M:
                risk = "PROBABLE_HUMAN_SHIELD"
                break
    return {
        "facility": best,
        "distance_meters": round(best_dist, 1),
        "risk_label": risk,
        "distance_method": best_distance_method,
    }


def _summary(facility_name: str, dist_m: float, risk: str) -> str:
    d = int(round(dist_m))
    if risk == "PROBABLE_HUMAN_SHIELD":
        return f"Strike within {d}m of {facility_name}. Suspected tunnel/military site also near this facility. Probable human shield scenario."
    if risk == "CRITICAL_PROXIMITY":
        return f"Strike within {d}m of {facility_name}. Critical proximity; high probability of collateral damage or dual-use."
    if risk == "HIGH_RISK":
        return f"Strike within {d}m of {facility_name}. High risk of collateral damage or dual-use."
    return f"Strike within {d}m of {facility_name}. Elevated risk; monitor for collateral impact."


def _parse_daypart(acquired: Any) -> str:
    s = str(acquired or "").strip()
    if not s:
        return "unknown"
    # Accept ISO or HHMM-like patterns from FIRMS payloads.
    hour: Optional[int] = None
    if "T" in s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
            hour = dt.hour
        except Exception:
            hour = None
    if hour is None and s.isdigit() and len(s) in (3, 4):
        try:
            hh = int(s[:-2]) if len(s) == 4 else int(s[0])
            hour = max(0, min(23, hh))
        except Exception:
            hour = None
    if hour is None:
        return "unknown"
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _vision_needed(base_risk: str, semantic: Dict[str, Any]) -> bool:
    if not PROXIMITY_VISION_ENABLED:
        return False
    severity_rank = {"ELEVATED": 1, "HIGH_RISK": 2, "CRITICAL_PROXIMITY": 3, "PROBABLE_HUMAN_SHIELD": 4}
    min_rank = severity_rank.get(PROXIMITY_VISION_MIN_RISK, 2)
    base_rank = severity_rank.get(base_risk, 0)
    sem_intensity = float(semantic.get("intensity", 0.0) or 0.0)
    return base_rank >= min_rank or sem_intensity >= 0.75


def _dynamic_risk_synthesis(
    base_risk: str,
    distance_m: float,
    facility_type: str,
    semantic: Dict[str, Any],
    vision: Dict[str, Any],
    acquired: Any,
) -> Dict[str, Any]:
    # Start from legacy risk for backward compatibility.
    score = 0.2
    if base_risk == "CRITICAL_PROXIMITY":
        score = 0.92
    elif base_risk == "PROBABLE_HUMAN_SHIELD":
        score = 0.88
    elif base_risk == "HIGH_RISK":
        score = 0.73
    elif base_risk == "ELEVATED":
        score = 0.5
    drivers: List[str] = [f"base_risk={base_risk}", f"distance_m={round(distance_m, 1)}"]
    sem_intensity = float(semantic.get("intensity", 0.0) or 0.0)
    if sem_intensity > 0:
        score += min(0.2, sem_intensity * 0.2)
        drivers.append(f"semantic_intensity={sem_intensity:.2f}")
    daypart = _parse_daypart(acquired)
    if "school" in (facility_type or "").lower() and daypart in ("morning", "day"):
        score += 0.08
        drivers.append(f"daypart_exposure={daypart}")
    if daypart == "night" and "school" in (facility_type or "").lower():
        score -= 0.05
        drivers.append("night_lower_school_occupancy")
    supports_tag = vision.get("supports_tag")
    vision_conf = float(vision.get("confidence", 0.0) or 0.0)
    if supports_tag is True:
        score += min(0.08, vision_conf * 0.08)
        drivers.append("vision_supports_osm_tag")
    elif supports_tag is False:
        score -= min(0.12, vision_conf * 0.12)
        drivers.append("vision_conflicts_with_osm_tag")
    score = max(0.0, min(1.0, score))
    if score >= 0.9:
        label = "CRITICAL_PROXIMITY"
    elif score >= 0.78:
        label = "HIGH_RISK"
    elif score >= 0.58:
        label = "ELEVATED"
    else:
        label = "LOW_CONFIDENCE"
    return {
        "risk_label_dynamic": label,
        "risk_confidence": round(score, 3),
        "risk_drivers": drivers[:8],
        "daypart": daypart,
    }


async def run_correlation_for_events(
    events: List[Dict[str, Any]],
    tunnel_sites_geojson: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    For each event (lat, lon, source?, description?), find nearest civilian facility using Overpass
    (batched union queries + TTL cache), optionally check tunnel_sites for PROBABLE_HUMAN_SHIELD.
    Returns list of evidence dicts.
    """
    tunnel_points = _tunnel_sites_from_geojson(tunnel_sites_geojson) if tunnel_sites_geojson else None
    evidence: List[Dict[str, Any]] = []
    seen_evidence: set[str] = set()

    valid: List[Tuple[float, float, Dict[str, Any]]] = []
    for ev in events:
        lat, lon = ev.get("lat"), ev.get("lon")
        if lat is None or lon is None:
            continue
        valid.append((float(lat), float(lon), ev))

    semantics_by_desc: Dict[str, Dict[str, Any]] = {}
    if PROXIMITY_SEMANTIC_ENABLED:
        descs = sorted(
            {
                str(ev.get("description") or "").strip()
                for _, _, ev in valid
                if str(ev.get("description") or "").strip()
            }
        )
        sem_results = await asyncio.gather(*[analyze_event_description(d) for d in descs], return_exceptions=True)
        for desc, sem in zip(descs, sem_results):
            semantics_by_desc[desc] = sem if isinstance(sem, dict) else {}

    # Distinct coordinates that are not yet in TTL cache → batch fetch (union query per chunk).
    need_fetch: List[Tuple[float, float]] = []
    seen_coord: set[Tuple[float, float]] = set()
    now_m = time.monotonic()
    for slat, slon, _ in valid:
        ck = _cache_key(slat, slon)
        async with _overpass_cache_lock:
            hit = ck in _overpass_cache and _overpass_cache[ck][0] > now_m
        if hit:
            continue
        if (slat, slon) in seen_coord:
            continue
        seen_coord.add((slat, slon))
        need_fetch.append((slat, slon))

    for batch_idx in range(0, len(need_fetch), OVERPASS_BATCH_SIZE):
        chunk = need_fetch[batch_idx : batch_idx + OVERPASS_BATCH_SIZE]
        if batch_idx > 0:
            await asyncio.sleep(OVERPASS_DELAY_S)
        try:
            await _fetch_and_cache_batch(chunk)
        except Exception:
            continue

    for slat, slon, ev in valid:
        key = _cache_key(slat, slon)
        async with _overpass_cache_lock:
            hit = _overpass_cache.get(key)
            now = time.monotonic()
            if hit and hit[0] > now:
                facilities: List[Dict[str, Any]] = list(hit[1])
            else:
                facilities = None
        if facilities is None:
            try:
                facilities = await fetch_overpass_context(slat, slon)
            except Exception:
                continue
        res = _nearest_and_risk(slat, slon, facilities, tunnel_points)
        if not res:
            continue
        fac = res["facility"]
        dedupe_key = f"{slat:.4f}-{slon:.4f}-{fac['id']}"
        if dedupe_key in seen_evidence:
            continue
        seen_evidence.add(dedupe_key)
        description = str(ev.get("description") or "").strip()
        semantic = semantics_by_desc.get(description, {}) if description else {}
        vision = {}
        if _vision_needed(res["risk_label"], semantic):
            try:
                vision = await verify_facility_visual(
                    facility_name=fac["name"],
                    facility_type=(fac.get("amenity") or fac.get("office") or "civilian infrastructure"),
                    facility_lat=float(fac["lat"]),
                    facility_lon=float(fac["lon"]),
                )
            except Exception:
                vision = {}
        dynamic = _dynamic_risk_synthesis(
            base_risk=res["risk_label"],
            distance_m=float(res["distance_meters"]),
            facility_type=(fac.get("amenity") or fac.get("office") or ""),
            semantic=semantic,
            vision=vision,
            acquired=ev.get("acquired"),
        )
        evidence.append(
            {
                "facilityName": fac["name"],
                "facilityType": fac.get("amenity") or fac.get("office") or "civilian infrastructure",
                "distanceMeters": res["distance_meters"],
                "riskLabel": res["risk_label"],
                "riskLabelDynamic": dynamic["risk_label_dynamic"] if PROXIMITY_ADVANCED_RISK_ENABLED else res["risk_label"],
                "riskConfidence": dynamic["risk_confidence"] if PROXIMITY_ADVANCED_RISK_ENABLED else None,
                "riskDrivers": dynamic["risk_drivers"] if PROXIMITY_ADVANCED_RISK_ENABLED else [],
                "geometryType": fac.get("geometry_type") or "point",
                "distanceMethod": res.get("distance_method") or "haversine_center",
                "semanticEventType": semantic.get("event_type"),
                "semanticIntensity": semantic.get("intensity"),
                "semanticConfidence": semantic.get("confidence"),
                "visionVerification": vision if isinstance(vision, dict) else {},
                "daypart": dynamic["daypart"] if PROXIMITY_ADVANCED_RISK_ENABLED else _parse_daypart(ev.get("acquired")),
                "strikeLat": slat,
                "strikeLon": slon,
                "facilityLat": fac["lat"],
                "facilityLon": fac["lon"],
                "summary": _summary(fac["name"], res["distance_meters"], res["risk_label"]),
                "source": ev.get("source"),
                "description": ev.get("description"),
                "strikeAcquired": ev.get("acquired"),
            }
        )
    return sorted(evidence, key=lambda x: x["distanceMeters"])
