"""
Proximity correlation: Overpass (schools/hospitals) + optional tunnel/sites GeoJSON.
Shared by api routes and PROXIMITY agent. Used for IRGC tunnel vs. civilian infrastructure (human shield).
"""
import logging
import math
from urllib.parse import quote
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RADIUS_M = 300
CRITICAL_M = 50
HIGH_RISK_M = 150
HUMAN_SHIELD_NEAR_M = 100


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two WGS84 points (Haversine)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})["amenity"~"school|hospital|place_of_worship"];
  way(around:{radius_m},{lat},{lon})["amenity"~"school|hospital|place_of_worship"];
  node(around:{radius_m},{lat},{lon})["office"="government"];
  way(around:{radius_m},{lat},{lon})["office"="government"];
);
out body center;
""".strip()


async def fetch_overpass_context(lat: float, lon: float) -> List[Dict[str, Any]]:
    """Return list of {id, name, lat, lon, amenity?, office?} for civilian facilities in radius."""
    query = _overpass_query(lat, lon, RADIUS_M)
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                OVERPASS_URL,
                content=f"data={quote(query)}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.info(
                "Overpass API rate limit (429); skipping facility context. "
                "Consider a self-hosted Overpass instance for higher throughput."
            )
        else:
            logger.warning("Overpass API error %s: %s", e.response.status_code, e)
        return []
    except Exception as e:
        logger.warning("Overpass request failed: %s", e)
        return []
    elements = data.get("elements") or []
    facilities = []
    seen = set()
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
        facilities.append({
            "id": str(el.get("id", key)),
            "name": name,
            "lat": flat,
            "lon": flon,
            "amenity": tags.get("amenity"),
            "office": tags.get("office"),
        })
    return facilities


def _tunnel_sites_from_geojson(fc: Dict[str, Any]) -> List[tuple[float, float]]:
    """Extract (lat, lon) from a GeoJSON FeatureCollection (points)."""
    out = []
    for f in (fc.get("features") or []):
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
    For each event (lat, lon, source?, description?), query Overpass, find nearest civilian facility,
    optionally check tunnel_sites for PROBABLE_HUMAN_SHIELD. Returns list of evidence dicts.
    """
    tunnel_points = _tunnel_sites_from_geojson(tunnel_sites_geojson) if tunnel_sites_geojson else None
    evidence = []
    seen = set()
    for ev in events:
        lat = ev.get("lat")
        lon = ev.get("lon")
        if lat is None or lon is None:
            continue
        try:
            facilities = await fetch_overpass_context(float(lat), float(lon))
        except Exception:
            continue
        res = _nearest_and_risk(float(lat), float(lon), facilities, tunnel_points)
        if not res:
            continue
        fac = res["facility"]
        key = f"{lat:.4f}-{lon:.4f}-{fac['id']}"
        if key in seen:
            continue
        seen.add(key)
        evidence.append({
            "facilityName": fac["name"],
            "facilityType": fac.get("amenity") or fac.get("office") or "civilian infrastructure",
            "distanceMeters": res["distance_meters"],
            "riskLabel": res["risk_label"],
            "strikeLat": float(lat),
            "strikeLon": float(lon),
            "facilityLat": fac["lat"],
            "facilityLon": fac["lon"],
            "summary": _summary(fac["name"], res["distance_meters"], res["risk_label"]),
            "source": ev.get("source"),
            "description": ev.get("description"),
            "strikeAcquired": ev.get("acquired"),
        })
    return sorted(evidence, key=lambda x: x["distanceMeters"])
