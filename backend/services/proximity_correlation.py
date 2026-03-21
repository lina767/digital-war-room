"""
Proximity correlation: Overpass (schools/hospitals) + optional tunnel/sites GeoJSON.
Shared by api routes and PROXIMITY agent. Used for IRGC tunnel vs. civilian infrastructure (human shield).

Overpass: batched union queries per run + in-memory TTL cache (per rounded lat/lon) to avoid one HTTP
request per strike and repeated identical coordinates.
"""

import asyncio
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

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
        lines.append(f'  node(around:{radius_m},{lat},{lon})["office"="government"];')
        lines.append(f'  way(around:{radius_m},{lat},{lon})["office"="government"];')
    inner = "\n".join(lines)
    return f"""
[out:json][timeout:25];
(
{inner}
);
out body center;
""".strip()


def _parse_overpass_elements(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Overpass JSON elements into deduplicated facility dicts."""
    elements = data.get("elements") or []
    facilities: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:en") or "Unnamed facility"
        if el.get("type") == "node":
            flat, flon = float(el.get("lat", 0)), float(el.get("lon", 0))
        elif el.get("type") == "way" and el.get("center"):
            c = el["center"]
            flat, flon = float(c.get("lat", 0)), float(c.get("lon", 0))
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
    for fac in facilities:
        d = haversine_m(strike_lat, strike_lon, fac["lat"], fac["lon"])
        if d < best_dist and d <= RADIUS_M:
            best_dist = d
            best = fac
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
        evidence.append(
            {
                "facilityName": fac["name"],
                "facilityType": fac.get("amenity") or fac.get("office") or "civilian infrastructure",
                "distanceMeters": res["distance_meters"],
                "riskLabel": res["risk_label"],
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
