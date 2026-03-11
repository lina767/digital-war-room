"""
SIGINT Agent – LangChain Tool-Calling Agent
Monitors military aircraft and naval vessels across multiple conflict regions.

ADS-B sources (no API key needed):
  - opendata.adsb.fi  (primary)
  - api.adsb.lol      (fallback)

Ship sources:
  - VesselFinder public endpoint (multiple bounding boxes)
  - Spire Maritime (subagent; optional SPIRE_MARITIME_API_KEY) – AIS/vessels in Persian Gulf, Red Sea, etc.
  - MarineTraffic RSS

Intelligence reports:
  - CriticalThreats, LongWarJournal, UnderstandingWar RSS feeds
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .llm import run_tool_agent

logger = logging.getLogger(__name__)

# ── ADS-B endpoints ───────────────────────────────────────────────────────
ADSB_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}",
    "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}",
]
ADSB_MIL_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/mil",
    "https://api.adsb.lol/v2/mil",
]

# ── Multiple regions for full Middle East coverage ────────────────────────
ADSB_REGIONS = [
    ("Persian Gulf", 26.0, 55.0, 400),
    ("Iraq/Iran", 33.0, 46.0, 400),
    ("Eastern Med", 33.0, 35.0, 350),
    ("Red Sea", 20.0, 40.0, 350),
]

# ── Classification ────────────────────────────────────────────────────────
MILITARY_CALLSIGN_PREFIXES = [
    "RCH", "USAF", "NAVY", "DUKE", "REACH", "JAKE", "EVAC", "SAM",
    "HAVOC", "VIPER", "SKULL", "IRON", "DOOM", "GHOST", "ATLAS", "SPAR",
]
SURVEILLANCE_TYPES = [
    "RC-135", "E-3", "E-8", "P-8", "EP-3", "RQ-4", "MQ-9", "U-2",
    "E-2", "E-6", "RC12", "MC-12", "P-3",
]
TANKER_TYPES = ["KC-135", "KC-10", "KC-46", "KC130"]
FIGHTER_TYPES = ["F-16", "F-15", "F-35", "F/A-18", "FA18", "B-52", "B-2", "B1"]
WARSHIP_KEYWORDS = [
    "warship", "destroyer", "frigate", "carrier", "corvette",
    "navy", "patrol", "amphibious", "cruiser", "military", "naval", "combat", "guard",
]
WARSHIP_PREFIXES = ["USS ", "HMS ", "FS ", "INS ", "USNS ", "RFS ", "IRIS "]
# AIS ship type 30-39 = military (ICAO/IEC 62287)
MILITARY_SHIP_TYPE_CODES = (30, 31, 32, 33, 34, 35, 36, 37, 38, 39)

# Spire Maritime (optional): legacy Vessels API – https://api.sense.spire.com/ (short token) or https://ais.spire.com/ (long token)
SPIRE_VESSELS_URL = "https://api.sense.spire.com/vessels"
SPIRE_REGIONS = [
    ("Persian Gulf", 22, 30, 48, 62),
    ("Red Sea", 12, 28, 32, 44),
    ("Eastern Med", 30, 37, 25, 38),
    ("Gulf of Aden", 10, 16, 42, 52),
]  # (label, lat_lo, lat_hi, lon_lo, lon_hi)

# Optional target aircraft profile (IAEA jet OE-III)
TARGET_AIRCRAFT: Dict[str, Dict[str, Any]] = {
    "OE-III": {
        # ICAO hex can be configured via env to avoid hard-coding
        "hex": (os.getenv("OEIII_HEX") or "").lower() or None,
        "regs": ["OE-III", "OEIII"],
        "notes": "IAEA / diplomatic jet",
    },
}

# Optional external APIs for target tracking (can be left unset in .env)
ADSBX_BASE_URL = os.getenv("ADSBX_BASE_URL", "").rstrip("/") or None
ADSBX_API_KEY = (os.getenv("ADSBX_API_KEY") or "").strip() or None
OPENSKY_USERNAME = (os.getenv("OPENSKY_USERNAME") or "").strip() or None
OPENSKY_PASSWORD = (os.getenv("OPENSKY_PASSWORD") or "").strip() or None


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_aircraft(callsign: str, ac_type: str) -> str | None:
    cs = (callsign or "").upper().strip()
    t = (ac_type or "").upper().strip()
    if any(x in t for x in FIGHTER_TYPES):
        return "fighter"
    if any(x in t for x in SURVEILLANCE_TYPES):
        return "surveillance"
    if any(x in t for x in TANKER_TYPES):
        return "tanker"
    if any(cs.startswith(p) for p in MILITARY_CALLSIGN_PREFIXES):
        return "transport"
    return None


def _in_conflict_zone(lat: float, lon: float) -> bool:
    return (10 <= lat <= 42) and (25 <= lon <= 65)


# ── Tools ──────────────────────────────────────────────────────────────────

def get_military_aircraft(region: str = "Middle East") -> List[Dict[str, Any]]:
    """
    Fetch military and surveillance aircraft across the full Middle East region.
    Queries multiple ADS-B regions: Persian Gulf, Iraq/Iran, Eastern Med, Red Sea.
    """
    async def _fetch_mil_global(client: httpx.AsyncClient) -> List[Dict]:
        for url in ADSB_MIL_ENDPOINTS:
            try:
                resp = await client.get(url, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    ac = data if isinstance(data, list) else data.get("ac", [])
                    if isinstance(ac, list) and ac:
                        return ac
            except Exception:
                continue
        return []

    async def _fetch_region(client: httpx.AsyncClient, lat: float, lon: float, dist: int) -> List[Dict]:
        for tpl in ADSB_ENDPOINTS:
            url = tpl.format(lat=lat, lon=lon, dist=dist)
            try:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 200:
                    data = resp.json()
                    ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                    if isinstance(ac, list):
                        return ac
            except Exception:
                continue
        return []

    async def _run():
        results = []
        seen_icao = set()
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            # Try global military endpoint first
            mil = await _fetch_mil_global(client)
            for ac in mil:
                lat = _safe_float(ac.get("lat"))
                lon = _safe_float(ac.get("lon"))
                if lat is None or lon is None or not _in_conflict_zone(lat, lon):
                    continue
                icao = str(ac.get("hex") or "").upper()
                if icao in seen_icao:
                    continue
                seen_icao.add(icao)
                callsign = str(ac.get("flight") or "").strip()
                ac_type = str(ac.get("t") or ac.get("type") or "").strip()
                results.append({
                    "flight": callsign or icao,
                    "type": ac_type,
                    "lat": lat, "lon": lon,
                    "category": _classify_aircraft(callsign, ac_type) or "military",
                    "source": "mil-global",
                })

            # Regional scans
            tasks = [_fetch_region(client, lat, lon, dist) for _, lat, lon, dist in ADSB_REGIONS]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)
            for (label, _, _, _), ac_list in zip(ADSB_REGIONS, all_results):
                if not isinstance(ac_list, list):
                    continue
                for ac in ac_list:
                    callsign = str(ac.get("flight") or "").strip()
                    ac_type = str(ac.get("t") or ac.get("type") or "").strip()
                    cat = _classify_aircraft(callsign, ac_type)
                    if not cat:
                        continue
                    icao = str(ac.get("hex") or "").upper()
                    if icao in seen_icao:
                        continue
                    seen_icao.add(icao)
                    lat = _safe_float(ac.get("lat"))
                    lon = _safe_float(ac.get("lon"))
                    if lat is None or lon is None:
                        continue
                    results.append({
                        "flight": callsign or ac_type or icao,
                        "type": ac_type, "lat": lat, "lon": lon,
                        "category": cat, "region": label,
                    })
        return results

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("SIGINT: get_military_aircraft failed: %s", e)
        return [{"error": str(e)}]


def _normalize_vessel(v: dict, label: str) -> dict | None:
    """Extract name, type, lat, lon from vessel dict (multiple possible field names)."""
    name = str(
        v.get("name") or v.get("NAME") or v.get("shipname") or v.get("vesselName") or ""
    ).strip()
    ship_type_raw = v.get("type") or v.get("TYPE") or v.get("shiptype") or v.get("vesselType")
    ship_type = str(ship_type_raw or "").strip()
    lat = _safe_float(v.get("lat") or v.get("latitude") or v.get("LAT"))
    lon = _safe_float(v.get("lon") or v.get("longitude") or v.get("LON"))
    # AIS military type codes 30-39
    try:
        t = int(float(ship_type_raw)) if ship_type_raw is not None else None
    except (TypeError, ValueError):
        t = None
    is_military_type = t in MILITARY_SHIP_TYPE_CODES
    is_warship = (
        is_military_type
        or any(kw in name.lower() or kw in ship_type.lower() for kw in WARSHIP_KEYWORDS)
        or any(name.upper().startswith(p.strip()) for p in WARSHIP_PREFIXES)
    )
    if not is_warship:
        return None
    return {
        "name": name or ship_type or "Vessel",
        "type": ship_type,
        "lat": lat,
        "lon": lon,
        "region": label,
    }


def get_naval_vessels(region: str = "Middle East") -> List[Dict[str, Any]]:
    """
    Fetch warships in the Persian Gulf, Red Sea, Eastern Med, and Gulf of Aden.
    Uses VesselFinder public map API; falls back to relaxed filter if no warships detected.
    """
    # bbox: try both "minLon,minLat,maxLon,maxLat" and "minLat,maxLat,minLon,maxLon"
    SHIP_REGIONS = [
        ("Persian Gulf", "48,22,62,30"),   # lon,lat,lon,lat
        ("Red Sea", "32,12,44,28"),
        ("Eastern Med", "25,30,38,37"),
        ("Gulf of Aden", "42,10,52,16"),
    ]

    async def _fetch(client: httpx.AsyncClient, bbox: str) -> List[Dict]:
        for param_name in ("bbox", "bb", "bounds"):
            try:
                resp = await client.get(
                    "https://www.vesselfinder.com/api/pub/vesselsonmap",
                    params={param_name: bbox}, timeout=12.0,
                )
                if resp.status_code != 200:
                    continue
                ct = (resp.headers.get("content-type") or "").lower()
                if "json" not in ct and "javascript" not in ct:
                    continue
                data = resp.json()
                if isinstance(data, list):
                    return data
                for key in ("vessels", "data", "rows", "results", "ships"):
                    if isinstance(data.get(key), list):
                        return data[key]
            except Exception:
                continue
        return []

    async def _run():
        results = []
        seen = set()
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SIGINT/1.0)"}) as client:
            tasks = [_fetch(client, bbox) for _, bbox in SHIP_REGIONS]
            all_vessels = await asyncio.gather(*tasks, return_exceptions=True)
            for (label, _), vessels in zip(SHIP_REGIONS, all_vessels):
                if not isinstance(vessels, list):
                    continue
                for v in vessels:
                    if not isinstance(v, dict):
                        continue
                    out = _normalize_vessel(v, label)
                    if not out:
                        continue
                    key = (out.get("name") or "").lower()[:40] or str(out.get("lat")) + "," + str(out.get("lon"))
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(out)
        return results

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("SIGINT: get_naval_vessels failed: %s", e)
        return [{"error": str(e)}]


def get_spire_vessels(region: str = "Middle East") -> List[Dict[str, Any]]:
    """
    Fetch vessel positions from Spire Maritime AIS (subagent). Requires SPIRE_MARITIME_API_KEY.
    Returns vessels in Persian Gulf, Red Sea, Eastern Med, Gulf of Aden. Filter client-side by bbox if API has no bbox param.
    """
    token = (os.getenv("SPIRE_MARITIME_API_KEY") or os.getenv("SPIRE_API_KEY") or "").strip()
    if not token:
        return []

    base_url = os.getenv("SPIRE_MARITIME_BASE_URL", "https://api.sense.spire.com").rstrip("/")
    url = f"{base_url}/vessels"

    async def _fetch():
        out = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Legacy API: limit; some versions support bbox. Fetch and filter by our regions.
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    params={"limit": 200},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                vessels = data if isinstance(data, list) else data.get("data", data.get("vessels", []))
                if not isinstance(vessels, list):
                    return []
                for v in vessels:
                    lat = _safe_float(v.get("latitude") or v.get("lat"))
                    lon = _safe_float(v.get("longitude") or v.get("lon"))
                    if lat is None or lon is None:
                        continue
                    for label, lat_lo, lat_hi, lon_lo, lon_hi in SPIRE_REGIONS:
                        if lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi:
                            name = v.get("name") or v.get("vessel_name") or "Vessel"
                            ship_type = v.get("type") or v.get("ship_type") or v.get("vessel_type") or ""
                            is_mil = any(
                                kw in (name or "").lower() or kw in (ship_type or "").lower()
                                for kw in WARSHIP_KEYWORDS
                            ) or (isinstance(v.get("type_of_ship"), int) and 30 <= v.get("type_of_ship", 0) <= 39)
                            out.append({
                                "name": name,
                                "type": ship_type or "unknown",
                                "lat": lat,
                                "lon": lon,
                                "region": label,
                                "source": "spire",
                            })
                            break
        except Exception as e:
            logger.debug("SIGINT: Spire vessels fetch failed: %s", e)
        return out[:80]

    try:
        return asyncio.run(_fetch())
    except Exception as e:
        logger.exception("SIGINT: get_spire_vessels failed: %s", e)
        return []


def get_conflict_reports(conflict: str = "Iran") -> List[Dict[str, Any]]:
    """
    Fetch recent military/conflict reports from diverse OSINT and media feeds:
    BBC, DW, Al Jazeera, RFE/RL, plus think tanks (CriticalThreats, LongWarJournal, UnderstandingWar).
    """
    CONFLICT_KEYWORDS = {
        "iran": ["iran", "irgc", "tehran", "hormuz", "houthi", "yemen", "persian gulf", "hezbollah", "idf", "lebanon"],
        "ukraine": ["ukraine", "russia", "kyiv", "donbas"],
        "israel": ["israel", "gaza", "hamas", "hezbollah", "idf"],
        "taiwan": ["taiwan", "pla", "strait", "china"],
    }
    cl = conflict.lower()
    keywords = next((v for k, v in CONFLICT_KEYWORDS.items() if k in cl), cl.split())

    async def _fetch():
        import re
        results = []
        # Gemischte Quellen: internationale Medien zuerst, dann Think-Tanks
        feeds = [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.dw.com/rdf/rss-en-world",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://www.criticalthreats.org/feed",
            "https://www.longwarjournal.org/feed",
            "https://understandingwar.org/rss.xml",
        ]
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            for feed_url in feeds:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        continue
                    items = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
                    for item in items[:15]:
                        title_m = re.search(r"<title>(.*?)</title>", item)
                        date_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
                        link_m = re.search(r"<link>(.*?)</link>", item)
                        title = re.sub(r"<[^>]+>|<!\[CDATA\[|\]\]>", "", title_m.group(1) if title_m else "").strip()
                        if not title or not any(kw in title.lower() for kw in keywords):
                            continue
                        results.append({
                            "title": title,
                            "date": date_m.group(1) if date_m else "",
                            "url": link_m.group(1) if link_m else "",
                            "source": feed_url.split("/")[2],
                        })
                except Exception:
                    continue
        return results[:10]

    try:
        return asyncio.run(_fetch())
    except Exception as e:
        logger.exception("SIGINT: get_conflict_reports failed: %s", e)
        return [{"error": str(e)}]


# ── Structured result models ────────────────────────────────────────────────

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScoreConfidence(BaseModel):
    level: str = "low"
    sources_ok: List[str] = Field(default_factory=list)
    sources_missing: List[str] = Field(default_factory=list)


class SigintResult(BaseModel):
    conflict: str
    aircraft: List[Dict[str, Any]] = Field(default_factory=list)
    ships: List[Dict[str, Any]] = Field(default_factory=list)
    conflict_reports: List[Dict[str, Any]] = Field(default_factory=list)
    notams: List[Dict[str, Any]] = Field(default_factory=list)
    sigint_score: float = 0.0
    alerts: List[str] = Field(default_factory=list)
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=_utc_iso)
    target_tracks: Dict[str, Any] = Field(default_factory=dict)


# ── Target aircraft tracking (OE-III, etc.) ─────────────────────────────────

def _match_target_aircraft(ac: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """Return True if ADS-B aircraft dict matches configured target (by hex, registration or callsign)."""
    if not isinstance(ac, dict):
        return False
    hex_cfg = (cfg.get("hex") or "").lower()
    regs = [r.upper() for r in (cfg.get("regs") or [])]

    icao24 = str(ac.get("hex") or ac.get("icao24") or "").lower()
    callsign = str(ac.get("flight") or ac.get("callsign") or "").upper().strip()
    reg = str(ac.get("r") or ac.get("registration") or "").upper().strip()

    if hex_cfg and icao24 and icao24 == hex_cfg:
        return True
    if reg and reg in regs:
        return True
    if callsign and any(cs in callsign for cs in regs):
        return True
    return False


def get_target_aircraft(target: str = "OE-III") -> Dict[str, Any]:
    """
    Track a specific high-value aircraft (e.g. IAEA jet OE-III) across multiple SIGINT layers.

    Combines:
    - ADSB-Exchange (unfiltered) when ADSBX_* env vars are set
    - OpenSky historical pattern (optional)
    - Existing ADS-B-based get_military_aircraft as a fallback
    """
    target_key = target.upper()
    cfg = TARGET_AIRCRAFT.get(target_key)
    if not cfg:
        return {"target": target, "error": "unknown_target"}

    async def _run() -> Dict[str, Any]:
        result: Dict[str, Any] = {"target": target_key}
        latest_adsbx: Optional[Dict[str, Any]] = None
        opensky_hint: Optional[Dict[str, Any]] = None

        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SIGINT/1.0)"}) as client:
            # 1. ADSB-Exchange live position (if configured)
            if ADSBX_BASE_URL and ADSBX_API_KEY:
                try:
                    # Broad Middle East / Europe search radius around eastern Med
                    url = f"{ADSBX_BASE_URL.rstrip('/')}/v2/lat/35/lon/25/dist/3000"
                    resp = await client.get(
                        url,
                        headers={"api-key": ADSBX_API_KEY},
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        ac_list = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                        if isinstance(ac_list, list):
                            candidates = [ac for ac in ac_list if _match_target_aircraft(ac, cfg)]
                            if candidates:
                                # take the most recently seen
                                ac = candidates[0]
                                lat = _safe_float(ac.get("lat"))
                                lon = _safe_float(ac.get("lon"))
                                latest_adsbx = {
                                    "lat": lat,
                                    "lon": lon,
                                    "alt_baro": _safe_float(ac.get("alt_baro") or ac.get("altitude")),
                                    "gs": _safe_float(ac.get("gs") or ac.get("groundspeed") or ac.get("speed")),
                                    "track": _safe_float(ac.get("track") or ac.get("heading")),
                                    "hex": ac.get("hex") or ac.get("icao24"),
                                    "callsign": ac.get("flight") or ac.get("callsign"),
                                    "registration": ac.get("r") or ac.get("registration"),
                                    "seen": ac.get("seen") or ac.get("timestamp"),
                                    "position_source": "adsbx",
                                }
                except Exception as e:
                    logger.debug("SIGINT: ADSB-Exchange target fetch failed: %s", e)

            # 2. OpenSky history (optional; good for pattern/historical last-seen)
            if OPENSKY_USERNAME and OPENSKY_PASSWORD and (cfg.get("hex") or "").lower():
                try:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    from_ts = now_ts - 24 * 3600
                    params = {
                        "icao24": (cfg.get("hex") or "").lower(),
                        "begin": from_ts,
                        "end": now_ts,
                    }
                    resp = await client.get(
                        "https://opensky-network.org/api/flights/aircraft",
                        params=params,
                        auth=(OPENSKY_USERNAME, OPENSKY_PASSWORD),
                        timeout=20.0,
                    )
                    if resp.status_code == 200:
                        flights = resp.json()
                        if isinstance(flights, list) and flights:
                            last = flights[-1]
                            opensky_hint = {
                                "last_callsign": last.get("callsign"),
                                "last_origin": last.get("estDepartureAirport"),
                                "last_destination": last.get("estArrivalAirport"),
                                "last_time": last.get("lastSeen") or last.get("firstSeen"),
                            }
                except Exception as e:
                    logger.debug("SIGINT: OpenSky history fetch failed: %s", e)

        # 3. Fallback: use existing ADS-B based military aircraft list and try to match target
        fallback_match: Optional[Dict[str, Any]] = None
        try:
            mil = get_military_aircraft() or []
            for ac in mil:
                if _match_target_aircraft(ac, cfg):
                    fallback_match = {
                        "flight": ac.get("flight"),
                        "lat": ac.get("lat"),
                        "lon": ac.get("lon"),
                        "type": ac.get("type"),
                        "category": ac.get("category"),
                        "source": ac.get("source", "mil-global"),
                        "position_source": "adsb",
                    }
                    break
        except Exception as e:
            logger.debug("SIGINT: fallback aircraft list for target failed: %s", e)

        result["adsbx"] = latest_adsbx
        result["opensky"] = opensky_hint
        result["fallback_sigint"] = fallback_match

        # derive a simple confidence flag for the target track
        if latest_adsbx:
            confidence = "high"
        elif fallback_match or opensky_hint:
            confidence = "medium"
        else:
            confidence = "low"
        result["confidence"] = confidence
        return result

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.exception("SIGINT: get_target_aircraft failed for %s: %s", target, e)
        return {"target": target, "error": str(e)}


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_sigint(conflict: str) -> Dict[str, Any]:
    """Execute SIGINT tool chain: aircraft → vessels → spire_vessels → conflict_reports → NOTAMs (iaea_tracker). No LLM."""
    from .iaea_tracker import fetch_notams

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            fut_air = executor.submit(get_military_aircraft)
            fut_ships = executor.submit(get_naval_vessels)
            fut_spire = executor.submit(get_spire_vessels)
            fut_reports = executor.submit(get_conflict_reports, conflict)
            fut_notams = executor.submit(lambda: fetch_notams(days=3, limit=15))
            fut_target = executor.submit(get_target_aircraft, "OE-III")

            try:
                raw_aircraft = fut_air.result(timeout=40)
            except Exception as e:
                logger.exception("SIGINT: aircraft fetch failed: %s", e)
                raw_aircraft = [{"error": str(e)}]

            try:
                raw_ships = fut_ships.result(timeout=40)
            except Exception as e:
                logger.exception("SIGINT: naval vessels fetch failed: %s", e)
                raw_ships = [{"error": str(e)}]

            try:
                raw_spire = fut_spire.result(timeout=40)
            except Exception as e:
                logger.debug("SIGINT: Spire vessels fetch in orchestrator failed: %s", e)
                raw_spire = []

            try:
                raw_reports = fut_reports.result(timeout=40)
            except Exception as e:
                logger.exception("SIGINT: conflict reports fetch failed: %s", e)
                raw_reports = [{"error": str(e)}]

            try:
                notam_result = fut_notams.result(timeout=40)
            except Exception as e:
                logger.exception("SIGINT: NOTAM fetch failed: %s", e)
                notam_result = {"notams": [], "error": str(e)}

            try:
                target_track = fut_target.result(timeout=40)
            except Exception as e:
                logger.debug("SIGINT: target aircraft tracking failed: %s", e)
                target_track = {"target": "OE-III", "error": str(e)}

        aircraft = [
            a for a in (raw_aircraft or [])
            if isinstance(a, dict) and "error" not in a
        ]
        ships = [
            s for s in (raw_ships or [])
            if isinstance(s, dict) and "error" not in s
        ]
        spire_ships = [
            s for s in (raw_spire or [])
            if isinstance(s, dict) and "error" not in s
        ]
        # merge Spire vessels into ships (dedup by name/position)
        seen_ship = {
            (s.get("name") or "").lower()[:40] or f"{s.get('lat')},{s.get('lon')}"
            for s in ships
        }
        for s in spire_ships:
            key = (s.get("name") or "").lower()[:40] or f"{s.get('lat')},{s.get('lon')}"
            if key not in seen_ship:
                seen_ship.add(key)
                ships.append(s)

        reports = [
            r for r in (raw_reports or [])
            if isinstance(r, dict) and "error" not in r
        ]
        notams = (notam_result.get("notams") or []) if isinstance(notam_result, dict) else []

        base = 30.0
        base += min(40, sum(10 for a in aircraft if a.get("category") == "surveillance"))
        base += sum(8 for a in aircraft if a.get("category") == "tanker")
        base += sum(12 for a in aircraft if a.get("category") == "fighter")
        base += min(25, len(ships) * 5)
        base += min(30, len(reports) * 8)
        score = max(0.0, min(100.0, base))

        alerts: List[str] = []
        if aircraft:
            by_cat: Dict[str, List] = {}
            for a in aircraft:
                by_cat.setdefault(a.get("category", "?"), []).append(a.get("flight", "?"))
            for cat, flights in by_cat.items():
                alerts.append(f"{len(flights)} {cat} aircraft: {', '.join(flights[:3])}")
        if ships:
            alerts.append(f"{len(ships)} warship(s) in region")
        if reports:
            alerts.append(f"{len(reports)} recent intel reports")
        if notams:
            alerts.append(f"{len(notams)} NOTAM(s) (airspace)")

        # score confidence based on which sources returned non-empty data
        sources_ok: List[str] = []
        sources_missing: List[str] = []
        for name, data in (
            ("aircraft", aircraft),
            ("ships", ships),
            ("spire_vessels", spire_ships),
            ("conflict_reports", reports),
            ("notams", notams),
        ):
            if data:
                sources_ok.append(name)
            else:
                sources_missing.append(name)
        if isinstance(target_track, dict) and not target_track.get("error") and (
            target_track.get("adsbx") or target_track.get("fallback_sigint") or target_track.get("opensky")
        ):
            sources_ok.append("target_OE-III")
        score_confidence = ScoreConfidence(
            level="high" if len(sources_ok) >= 2 else "low",
            sources_ok=sources_ok,
            sources_missing=sources_missing,
        )

        if not aircraft and not ships and not reports and not notams:
            logger.warning(
                "SIGINT: All sources empty for conflict '%s' (no aircraft, ships, reports, NOTAMs).",
                conflict,
            )

        result = SigintResult(
            conflict=conflict,
            aircraft=aircraft,
            ships=ships,
            conflict_reports=reports,
            notams=notams,
            sigint_score=round(score, 1),
            alerts=alerts,
            summary=(
                f"SIGINT (rule-based): {len(aircraft)} aircraft, "
                f"{len(ships)} ships, {len(reports)} reports, {len(notams)} NOTAMs. "
                f"Score {score:.0f}."
            ),
            score_confidence=score_confidence,
            target_tracks={"OE-III": target_track} if isinstance(target_track, dict) else {},
        )
        return result.model_dump(mode="json")
    except Exception as e:
        logger.exception("SIGINT: rule-based pipeline failed for conflict '%s': %s", conflict, e)
        return {
            "conflict": conflict,
            "aircraft": [],
            "ships": [],
            "conflict_reports": [],
            "notams": [],
            "sigint_score": 30.0,
            "alerts": [],
            "summary": "SIGINT error: pipeline failed.",
        }


# ── Agent ──────────────────────────────────────────────────────────────────

SIGINT_SYSTEM = """You are a SIGINT analyst monitoring military movements and conflict activity.
Call all three tools, compute a score (0-100), return ONLY valid JSON:

Scoring:
- Base: 30
- Surveillance aircraft: +10 each (max +40)
- Tanker aircraft (strike prep): +8 each
- Fighter aircraft: +12 each
- Warships: +5 each (max +25)
- Conflict reports (airstrikes, attacks): +8 each (max +30)
- Clamp to [0, 100]

{
  "aircraft": [...],
  "ships": [...],
  "conflict_reports": [...],
  "sigint_score": <number>,
  "alerts": ["<alert>", ...],
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


def run_sigint_agent(conflict: str) -> Dict[str, Any]:
    """Run SIGINT: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    import json
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_sigint(conflict)

    TOOL_FNS = {
        "get_military_aircraft": get_military_aircraft,
        "get_naval_vessels": get_naval_vessels,
        "get_spire_vessels": get_spire_vessels,
        "get_conflict_reports": get_conflict_reports,
    }
    TOOL_SCHEMAS = [
        {"name": "get_military_aircraft", "description": "Fetch military aircraft in conflict regions via ADS-B.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_naval_vessels", "description": "Fetch naval vessels in conflict regions.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_spire_vessels", "description": "Fetch Spire Maritime AIS vessel data.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_conflict_reports", "description": "Fetch conflict intelligence reports from RSS feeds.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    ]
    text = run_tool_agent(
        system=SIGINT_SYSTEM,
        user_content=f"Monitor military movements for conflict: {conflict}",
        tool_fns=TOOL_FNS,
        tool_schemas=TOOL_SCHEMAS,
        max_rounds=6,
    )
    if text:
        text = text.strip()
        for p in ("```json", "```"):
            if text.startswith(p):
                text = text[len(p):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        try:
            result = json.loads(text)
            result["conflict"] = conflict
            return result
        except Exception:
            pass
    return _run_rule_based_sigint(conflict)
