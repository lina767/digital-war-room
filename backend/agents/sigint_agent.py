import asyncio
from typing import Any, Dict, List, Tuple

import httpx


ADSB_URL = "https://opendata.adsb.fi/api/v2/lat/27.0/lon/55.0/dist/250"
VESSELFINDER_URL = "https://www.vesselfinder.com/api/pub/vesselsonmap"
MARINETRAFFIC_URL = "https://www.marinetraffic.com/getData/get_data_json_4"

MILITARY_CALLSIGNS = [
    "RCH",
    "USAF",
    "NAVY",
    "DUKE",
    "REACH",
    "JAKE",
    "EVAC",
    "GTMO",
    "SAM",
    "AIR1",
    "AIR2",
]

SURVEILLANCE_TYPES = [
    "RC-135",
    "E-3",
    "E-8",
    "P-8",
    "EP-3",
    "RQ-4",
    "MQ-9",
    "U-2",
    "E-6",
]

TANKER_TYPES = [
    "KC-135",
    "KC-10",
    "KC-46",
]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _fetch_adsb_aircraft(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(ADSB_URL)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    data = resp.json()

    # ADSB.fi may return a dict with "ac" or "aircraft" or a bare list
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("ac", "aircraft", "states"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _classify_aircraft(callsign: str, ac_type: str) -> str | None:
    cs_upper = callsign.upper()
    type_upper = ac_type.upper()

    if any(cs_upper.startswith(prefix) for prefix in MILITARY_CALLSIGNS):
        # Callsigns like RCH, REACH, etc are usually transport or tanker
        if any(t in type_upper for t in TANKER_TYPES):
            return "tanker"
        return "transport"

    if any(t in type_upper for t in SURVEILLANCE_TYPES):
        return "surveillance"

    if any(t in type_upper for t in TANKER_TYPES):
        return "tanker"

    return None


def _extract_aircraft_position(raw: Dict[str, Any]) -> Tuple[float | None, float | None, int | None]:
    lat = _safe_float(raw.get("lat") or raw.get("latitude"))
    lon = _safe_float(raw.get("lon") or raw.get("longitude"))

    alt = raw.get("alt_baro") or raw.get("altitude") or raw.get("alt")
    alt_ft = None
    if alt is not None:
        try:
            alt_ft = int(float(alt))
        except (TypeError, ValueError):
            alt_ft = None

    return lat, lon, alt_ft


def _filter_aircraft(aircraft_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for ac in aircraft_raw:
        callsign = (
            (ac.get("flight") or ac.get("callsign") or ac.get("cs") or "").strip()
        )
        ac_type = (
            ac.get("type")
            or ac.get("t")
            or ac.get("aircraft_type")
            or ac.get("desc")
            or ""
        )

        if not callsign and not ac_type:
            continue

        category = _classify_aircraft(callsign, ac_type)
        if category is None:
            continue

        lat, lon, alt_ft = _extract_aircraft_position(ac)
        if lat is None or lon is None:
            continue

        results.append(
            {
                "callsign": callsign or None,
                "type": ac_type or None,
                "lat": lat,
                "lon": lon,
                "altitude": alt_ft,
                "category": category,
            }
        )

    return results


async def _fetch_vessels_vesselfinder(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    # Public "vesselsonmap" endpoint used by the website; format is not formally documented,
    # so we treat it as best-effort JSON.
    try:
        resp = await client.get(VESSELFINDER_URL, params={"bbox": "48,22,62,30"})
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("vessels", "data", "rows"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def _fetch_vessels_marinetraffic(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(MARINETRAFFIC_URL)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("vessels", "data", "rows"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def _fetch_ships(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    # Try VesselFinder first, fall back to MarineTraffic if it fails
    try:
        vessels = await _fetch_vessels_vesselfinder(client)
        if vessels:
            return vessels
    except httpx.HTTPError:
        pass

    try:
        vessels = await _fetch_vessels_marinetraffic(client)
        return vessels
    except httpx.HTTPError:
        return []


def _is_warship(name: str, ship_type: str) -> bool:
    name_l = name.lower()
    type_l = ship_type.lower()

    keywords = [
        "warship",
        "military",
        "destroyer",
        "frigate",
        "corvette",
        "carrier",
        "aircraft carrier",
        "navy",
        "patrol boat",
        "patrol vessel",
    ]

    for kw in keywords:
        if kw in name_l or kw in type_l:
            return True

    # Common hull prefixes
    if any(prefix in name for prefix in ("USS ", "HMS ", "FS ", "FREMM ")):
        return True

    return False


def _extract_ship_position(raw: Dict[str, Any]) -> Tuple[float | None, float | None]:
    lat = _safe_float(raw.get("lat") or raw.get("LATITUDE"))
    lon = _safe_float(raw.get("lon") or raw.get("LONGITUDE"))
    return lat, lon


def _filter_ships(vessels_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for v in vessels_raw:
        # Try to normalize common field names across providers
        name = (
            v.get("name")
            or v.get("NAME")
            or v.get("shipname")
            or v.get("SHIPNAME")
            or ""
        )
        ship_type = (
            v.get("type")
            or v.get("TYPE")
            or v.get("ship_type")
            or v.get("SHIPTYPE")
            or ""
        )

        # Some providers nest AIS-related data
        if isinstance(v.get("AIS"), dict):
            ais = v["AIS"]
            name = ais.get("NAME", name)
            ship_type = ais.get("TYPE", ship_type)

        name = str(name or "").strip()
        ship_type = str(ship_type or "").strip()

        if not name and not ship_type:
            continue

        if not _is_warship(name, ship_type):
            continue

        lat, lon = _extract_ship_position(v)
        if lat is None or lon is None:
            continue

        results.append(
            {
                "name": name or None,
                "type": ship_type or None,
                "lat": lat,
                "lon": lon,
            }
        )

    return results


def _compute_sigint_score(aircraft: List[Dict[str, Any]], ships: List[Dict[str, Any]]) -> float:
    score = 30.0

    num_surv = sum(1 for a in aircraft if a.get("category") == "surveillance")
    num_tanker = sum(1 for a in aircraft if a.get("category") == "tanker")
    num_warships = len(ships)

    score += min(num_surv * 10.0, 40.0)
    score += num_tanker * 8.0
    score += min(num_warships * 5.0, 20.0)

    return max(0.0, min(100.0, score))


def _build_summary(aircraft: List[Dict[str, Any]], ships: List[Dict[str, Any]], score: float) -> str:
    num_aircraft = len(aircraft)
    num_warships = len(ships)
    return (
        f"{num_aircraft} military-relevant aircraft detected, "
        f"{num_warships} likely warships in region. "
        f"SIGINT activity score: {score:.1f}."
    )


def _build_alerts(aircraft: List[Dict[str, Any]], ships: List[Dict[str, Any]]) -> List[str]:
    alerts: List[str] = []

    for ac in aircraft:
        category = ac.get("category")
        ac_type = str(ac.get("type") or "").upper()
        callsign = ac.get("callsign") or "Unknown"
        if category == "surveillance":
            alerts.append(f"{ac_type or 'Surveillance aircraft'} ({callsign}) detected - active ISR mission.")
        elif category == "tanker":
            alerts.append(f"Tanker ({callsign}) detected - indicates sustained air operations.")

    for ship in ships:
        name = ship.get("name") or "Warship"
        alerts.append(f"{name} detected in Persian Gulf - naval presence heightened.")

    # Deduplicate while preserving order and avoid overly long lists
    seen = set()
    unique_alerts: List[str] = []
    for alert in alerts:
        if alert not in seen:
            seen.add(alert)
            unique_alerts.append(alert)
        if len(unique_alerts) >= 10:
            break

    return unique_alerts


async def _run_sigint_agent_async(conflict: str) -> Dict[str, Any]:  # conflict kept for interface symmetry
    async with httpx.AsyncClient(timeout=15.0) as client:
        aircraft_raw, ships_raw = await asyncio.gather(
            _fetch_adsb_aircraft(client),
            _fetch_ships(client),
        )

    aircraft = _filter_aircraft(aircraft_raw)
    ships = _filter_ships(ships_raw)

    sigint_score = _compute_sigint_score(aircraft, ships)
    summary = _build_summary(aircraft, ships, sigint_score)
    alerts = _build_alerts(aircraft, ships)

    return {
        "conflict": conflict,
        "aircraft": aircraft,
        "ships": ships,
        "sigint_score": sigint_score,
        "summary": summary,
        "alerts": alerts,
    }


def run_sigint_agent(conflict: str) -> Dict[str, Any]:
    """
    Public sync entrypoint for the SIGINT agent.

    Uses async httpx under the hood but exposes a synchronous API
    for consistency with other agents.
    """
    return asyncio.run(_run_sigint_agent_async(conflict))

