"""
SIGINT Agent – LangChain Tool-Calling Agent
Monitors military aircraft and naval vessels across multiple conflict regions.

ADS-B sources (no API key needed):
  - opendata.adsb.fi  (primary)
  - api.adsb.lol      (fallback)

Optional: ADSBexchange via RapidAPI (ADSBEXCHANGE_RAPIDAPI_KEY) for target tracking (e.g. OE-III).
  - https://rapidapi.com/adsbx/api/adsbexchange-com1

Naval vessels: no external API in use (VesselFinder removed). Ships list can be extended via Chokepoint/AISStream or future source.

Intelligence reports:
  - CriticalThreats, LongWarJournal, UnderstandingWar RSS feeds
"""
import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .config import USER_AGENT, DEFAULT_TIMEOUT
from .health_registry import get_health_registry
from .llm import run_agent_with_fallback
from .utils import (
    AgentMetadata,
    SourceResult,
    safe_float,
    utc_now_iso,
    parse_adsb_response,
    ScoreConfidence,
    run_async,
    compute_confidence_from_sources,
)

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
    "FORTE",    # RQ-4 Global Hawk (FORTE11, FORTE12, etc.)
    "TACAMO",   # E-6B Mercury (nuclear C3)
    "NCHO",     # E-6B / TACAMO alternate
]
SURVEILLANCE_TYPES = [
    "RC-135", "E-3", "E-8", "P-8", "EP-3", "RQ-4", "MQ-9", "U-2",
    "E-2", "E-6", "RC12", "MC-12", "P-3",
    "E-7",      # E-7A Wedgetail (drone/cruise missile detection)
    "E7A",
    "E6B",      # E-6B Mercury (TACAMO – nuclear C3, doomsday plane)
]
TANKER_TYPES = [
    "KC-135", "KC-10", "KC-46", "KC130",
    "A330",     # A330 MRTT (Israel/NATO/UAE – long-range refueling)
    "MRTT",
    "A310",     # A310 MRTT (Luftwaffe)
    "KC-30",    # RAAF A330 MRTT designation
]
FIGHTER_TYPES = ["F-16", "F-15", "F-35", "F/A-18", "FA18", "B-52", "B-2", "B1"]
TRANSPORT_TYPES = [
    "C-17", "C-130", "C-5", "C-40", "C-37", "C-32",
    "Il-76", "IL76",   # Pouya Air / Iranian military transport
    "An-124", "AN124",
    "747",              # Qeshm Fars Air 747F (EP-FAA, EP-FAB)
]
DOOMSDAY_TYPES = [
    "E-6",  "E6B",     # E-6B Mercury (TACAMO – nuclear C3)
    "E-4",  "E4B",     # E-4B Nightwatch (NAOC)
]
# Callsign patterns that indicate high-priority intel events
HIGH_PRIORITY_CALLSIGNS = [
    "FORTE",            # RQ-4 Global Hawk ISR
    "TACAMO",           # E-6B Mercury
    "NCHO",             # E-6B alternate
    "DARKSTAR",         # classified ISR
    "GORDO",            # RQ-4 alternate
]
# Hormuz tankers: filled from Chokepoint agent (AISStream) in supervisor when AIRSTREAM_API_KEY is set.

# Optional target aircraft profiles – track multiple high-value aircraft via ADSBexchange/RapidAPI + free ADS-B.
# Add entries here or via env (e.g. OEIII_HEX for ICAO). Each key = target name, value = { hex?, regs?, notes? }.
# OEIII_HEX: set in .env if known (e.g. from ADSBexchange) for reliable ICAO lookup
def _target_aircraft_from_env() -> Dict[str, Dict[str, Any]]:
    targets: Dict[str, Dict[str, Any]] = {
        # ── IAEA / Diplomatic ────────────────────────────────────────
        "OE-III": {
            "hex": (os.getenv("OEIII_HEX") or "").lower() or None,
            "regs": ["OE-III", "OEIII", "OE III"],
            "notes": "IAEA / diplomatic jet (Rafael Grossi)",
        },
        # ── Iranian high-value (arms logistics, government) ──────────
        "EP-FAA": {
            "hex": (os.getenv("TARGET_EPFAA_HEX") or "").lower() or None,
            "regs": ["EP-FAA", "EPFAA"],
            "notes": "Qeshm Fars Air 747F – linked to IRGC arms shipments (Syria corridor)",
        },
        "EP-FAB": {
            "hex": (os.getenv("TARGET_EPFAB_HEX") or "").lower() or None,
            "regs": ["EP-FAB", "EPFAB"],
            "notes": "Qeshm Fars Air 747F – linked to IRGC arms shipments",
        },
        "EP-IGA": {
            "hex": (os.getenv("TARGET_EPIGA_HEX") or "").lower() or None,
            "regs": ["EP-IGA", "EPIGA"],
            "notes": "Iran government A340 – senior leadership transport",
        },
        "EP-IGC": {
            "hex": (os.getenv("TARGET_EPIGC_HEX") or "").lower() or None,
            "regs": ["EP-IGC", "EPIGC"],
            "notes": "Iran government Falcon 900 – leadership transport",
        },
    }
    # Pouya Air Il-76 – no fixed reg known publicly; match by operator callsign if available
    targets["POUYA"] = {
        "hex": (os.getenv("TARGET_POUYA_HEX") or "").lower() or None,
        "regs": ["IRZ", "POUYA"],  # IRZ = Pouya Air ICAO code
        "notes": "Pouya Air Il-76 – military transport within region",
    }
    # Custom targets from env (e.g. TARGET_AIRCRAFT_EXTRA=AF1,RAFSHADOW1)
    extra = (os.getenv("TARGET_AIRCRAFT_EXTRA") or "").strip()
    for name in [x.strip().upper() for x in extra.split(",") if x.strip()]:
        if name in targets:
            continue
        hex_val = (os.getenv(f"TARGET_{name.replace('-', '_')}_HEX") or "").lower() or None
        targets[name] = {"hex": hex_val, "regs": [name, name.replace("-", "")], "notes": "Custom target"}
    return targets


TARGET_AIRCRAFT: Dict[str, Dict[str, Any]] = _target_aircraft_from_env()

# Free ADS-B registration/region endpoints (no key) – used for OE-III before paid APIs
ADSB_REGISTRATION_URLS = [
    "https://opendata.adsb.fi/api/v2/registration/{reg}",
    "https://api.adsb.lol/v2/registration/{reg}",
]
# Scan regions for target aircraft tracking – covers key bases and corridors
ADSB_TARGET_SCAN_REGIONS = [
    # Original IAEA/OE-III corridors
    ("Vienna/Austria", 48.2, 16.4, 350),
    ("Eastern Med", 33.0, 35.0, 400),
    ("Persian Gulf", 26.0, 55.0, 450),
    # Key military bases & transit corridors
    ("Al Udeid/Qatar", 25.1, 51.3, 200),      # CENTCOM forward HQ
    ("Al Dhafra/UAE", 24.2, 54.5, 200),        # US/French air base
    ("Akrotiri/Cyprus", 34.6, 33.0, 250),      # RAF base (staging)
    ("Jordan corridor", 31.5, 36.5, 300),      # transit corridor → Iran
    ("Northern Iraq", 36.0, 44.0, 300),         # Erbil/Kirkuk corridor
    ("Strait of Hormuz", 26.5, 56.3, 200),     # maritime ISR (P-8)
    ("Tehran FIR", 35.7, 51.4, 400),           # Iranian airspace
    ("Syria corridor", 34.5, 38.5, 300),       # Damascus/Aleppo (arms flights)
]
# Backwards compat alias
ADSB_REGIONS_OEIII = ADSB_TARGET_SCAN_REGIONS

# Optional external APIs for target tracking (can be left unset in .env)
ADSBX_BASE_URL = os.getenv("ADSBX_BASE_URL", "").rstrip("/") or None
ADSBX_API_KEY = (os.getenv("ADSBX_API_KEY") or "").strip() or None
ADSBEXCHANGE_RAPIDAPI_KEY = (os.getenv("ADSBEXCHANGE_RAPIDAPI_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip() or None
ADSBEXCHANGE_RAPIDAPI_HOST = (os.getenv("ADSBEXCHANGE_RAPIDAPI_HOST") or "adsbexchange-com1.p.rapidapi.com").strip()
OPENSKY_USERNAME = (os.getenv("OPENSKY_USERNAME") or "").strip() or None
OPENSKY_PASSWORD = (os.getenv("OPENSKY_PASSWORD") or "").strip() or None



def _adsbexchange_rapidapi_headers() -> Dict[str, str]:
    return {
        "X-RapidAPI-Key": ADSBEXCHANGE_RAPIDAPI_KEY or "",
        "X-RapidAPI-Host": ADSBEXCHANGE_RAPIDAPI_HOST,
        "User-Agent": USER_AGENT,
    }


async def _fetch_adsbexchange_rapidapi(
    client: httpx.AsyncClient,
    *,
    icao: Optional[str] = None,
    callsign: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    dist_nm: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch aircraft from ADSBexchange via RapidAPI.
    One of: icao=HEX, callsign=CALLSIGN, or (lat, lon, dist_nm) for region (max 100 nm per request).
    """
    if not ADSBEXCHANGE_RAPIDAPI_KEY:
        return []
    base = f"https://{ADSBEXCHANGE_RAPIDAPI_HOST}"
    headers = _adsbexchange_rapidapi_headers()
    ac_list: List[Dict[str, Any]] = []
    try:
        if icao:
            url = f"{base}/api/aircraft/icao/{icao.strip().upper()}"
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                if isinstance(ac, list):
                    ac_list = ac
                elif isinstance(ac, dict):
                    ac_list = [ac]
        elif callsign and callsign.strip():
            url = f"{base}/api/aircraft/call/{callsign.strip().upper()}"
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                if isinstance(ac, list):
                    ac_list = ac
                elif isinstance(ac, dict):
                    ac_list = [ac]
        elif lat is not None and lon is not None:
            dist = min(100, max(1, int(dist_nm)))
            url = f"{base}/api/aircraft/lat/{lat}/lon/{lon}/dist/{dist}"
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                ac_list = parse_adsb_response(resp.json())
    except Exception as e:
        logger.debug("SIGINT: ADSBexchange RapidAPI fetch failed: %s", e)
    return ac_list


async def _fetch_adsb_by_registration(client: httpx.AsyncClient, reg: str) -> List[Dict[str, Any]]:
    """Free OE-III lookup by registration (adsb.fi, adsb.lol). Reg without hyphen, e.g. OEIII."""
    reg_clean = (reg or "").replace("-", "").replace(" ", "").strip().upper()
    if not reg_clean:
        return []
    for tpl in ADSB_REGISTRATION_URLS:
        try:
            url = tpl.format(reg=reg_clean)
            resp = await client.get(url, timeout=12.0)
            if resp.status_code != 200:
                continue
            ac = parse_adsb_response(resp.json())
            if ac:
                return ac
        except Exception as e:
            logger.debug("SIGINT: adsb registration %s failed: %s", tpl[:40], e)
    return []


async def _fetch_adsb_regions_for_target(
    client: httpx.AsyncClient, cfg: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Scan Vienna, Eastern Med, Gulf via adsb.fi/adsb.lol and return aircraft matching target."""
    candidates: List[Dict[str, Any]] = []
    for _label, lat, lon, dist in ADSB_REGIONS_OEIII:
        for tpl in ADSB_ENDPOINTS:
            try:
                url = tpl.format(lat=lat, lon=lon, dist=min(500, dist))
                resp = await client.get(url, timeout=12.0)
                if resp.status_code != 200:
                    continue
                ac_list = parse_adsb_response(resp.json())
                if ac_list:
                    for ac in ac_list:
                        if _match_target_aircraft(ac, cfg):
                            candidates.append(ac)
                    if candidates:
                        return candidates
            except Exception:
                continue
        await asyncio.sleep(0.35)
    return candidates


def _classify_aircraft(callsign: str, ac_type: str, reg: str = "") -> str | None:
    cs = (callsign or "").upper().strip()
    t = (ac_type or "").upper().strip()
    r = (reg or "").upper().strip()
    if any(x in t for x in DOOMSDAY_TYPES) or any(cs.startswith(p) for p in ("TACAMO", "NCHO")):
        return "doomsday"
    if any(x in t for x in FIGHTER_TYPES):
        return "fighter"
    if any(x in t for x in SURVEILLANCE_TYPES):
        return "surveillance"
    if any(cs.startswith(p) for p in HIGH_PRIORITY_CALLSIGNS):
        return "surveillance"
    if any(x in t for x in TANKER_TYPES):
        return "tanker"
    if any(x in t for x in TRANSPORT_TYPES):
        return "transport"
    if r.startswith("EP-") and any(x in t for x in ("747", "A340", "F900", "IL76")):
        return "iranian_gov"
    if any(cs.startswith(p) for p in MILITARY_CALLSIGN_PREFIXES):
        return "military"
    return None


def _in_conflict_zone(lat: float, lon: float) -> bool:
    from compliance.zones import in_conflict_zone
    return in_conflict_zone(lat, lon)


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
                lat = safe_float(ac.get("lat"))
                lon = safe_float(ac.get("lon"))
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

            # Regional scans (free: adsb.fi, adsb.lol)
            tasks = [_fetch_region(client, lat, lon, dist) for _, lat, lon, dist in ADSB_REGIONS]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)
            for (label, _, _, _), ac_list in zip(ADSB_REGIONS, all_results):
                if not isinstance(ac_list, list):
                    continue
                for ac in ac_list:
                    callsign = str(ac.get("flight") or "").strip()
                    ac_type = str(ac.get("t") or ac.get("type") or "").strip()
                    reg = str(ac.get("r") or ac.get("reg") or "").strip()
                    cat = _classify_aircraft(callsign, ac_type, reg)
                    if not cat:
                        continue
                    icao = str(ac.get("hex") or "").upper()
                    if icao in seen_icao:
                        continue
                    seen_icao.add(icao)
                    lat = safe_float(ac.get("lat"))
                    lon = safe_float(ac.get("lon"))
                    if lat is None or lon is None:
                        continue
                    results.append({
                        "flight": callsign or ac_type or icao,
                        "type": ac_type, "lat": lat, "lon": lon,
                        "category": cat, "region": label,
                        "reg": reg or None,
                    })

            # ADSBexchange RapidAPI (paid): extra region scans (2 circles per region for better coverage)
            if ADSBEXCHANGE_RAPIDAPI_KEY:
                # Primary center + offset center per region to cover more than 100 nm
                for label, lat, lon, dist in ADSB_REGIONS:
                    for lat_off, lon_off in [(0, 0), (0.6, 0.6)]:
                        try:
                            ac_list_rapid = await _fetch_adsbexchange_rapidapi(
                                client,
                                lat=lat + lat_off,
                                lon=lon + lon_off,
                                dist_nm=min(100, dist),
                            )
                            for ac in ac_list_rapid or []:
                                callsign = str(ac.get("flight") or "").strip()
                                ac_type = str(ac.get("t") or ac.get("type") or "").strip()
                                reg = str(ac.get("r") or ac.get("reg") or "").strip()
                                cat = _classify_aircraft(callsign, ac_type, reg)
                                if not cat:
                                    continue
                                icao = str(ac.get("hex") or "").upper()
                                if icao in seen_icao:
                                    continue
                                lat_f = safe_float(ac.get("lat"))
                                lon_f = safe_float(ac.get("lon"))
                                if lat_f is None or lon_f is None or not _in_conflict_zone(lat_f, lon_f):
                                    continue
                                seen_icao.add(icao)
                                results.append({
                                    "flight": callsign or ac_type or icao,
                                    "type": ac_type,
                                    "lat": lat_f,
                                    "lon": lon_f,
                                    "category": cat,
                                    "region": label,
                                    "reg": reg or None,
                                    "source": "adsbexchange",
                                })
                        except Exception as e:
                            logger.debug("SIGINT: ADSBexchange RapidAPI region %s failed: %s", label, e)
        return results

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception("SIGINT: get_military_aircraft failed: %s", e)
        return [{"error": str(e)}]


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
        return run_async(_fetch())
    except Exception as e:
        logger.exception("SIGINT: get_conflict_reports failed: %s", e)
        return [{"error": str(e)}]


# ── Structured result models ────────────────────────────────────────────────

class SigintResult(BaseModel):
    conflict: str
    aircraft: List[Dict[str, Any]] = Field(default_factory=list)
    ships: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tankers: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tanker_count: int = 0
    conflict_reports: List[Dict[str, Any]] = Field(default_factory=list)
    notams: List[Dict[str, Any]] = Field(default_factory=list)
    sigint_score: float = 0.0
    alerts: List[str] = Field(default_factory=list)
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=utc_now_iso)
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

    Order: (0) Free registration lookup adsb.fi/adsb.lol, (0b) free region scan,
    (1a) RapidAPI, (1b) ADSB-Exchange direct, (2) OpenSky, (3) military list.
    Set OEIII_HEX in .env for reliable ICAO lookups when known.
    """
    target_key = target.upper()
    cfg = TARGET_AIRCRAFT.get(target_key)
    if not cfg:
        return {"target": target, "error": "unknown_target"}

    def _ac_to_position(ac: Dict[str, Any], source: str) -> Dict[str, Any]:
        return {
            "lat": safe_float(ac.get("lat")),
            "lon": safe_float(ac.get("lon")),
            "alt_baro": safe_float(ac.get("alt_baro") or ac.get("altitude")),
            "gs": safe_float(ac.get("gs") or ac.get("groundspeed") or ac.get("speed")),
            "track": safe_float(ac.get("track") or ac.get("heading")),
            "hex": ac.get("hex") or ac.get("icao24"),
            "callsign": ac.get("flight") or ac.get("callsign"),
            "registration": ac.get("r") or ac.get("registration"),
            "seen": ac.get("seen") or ac.get("timestamp"),
            "position_source": source,
        }

    async def _run() -> Dict[str, Any]:
        result: Dict[str, Any] = {"target": target_key}
        latest_adsbx: Optional[Dict[str, Any]] = None
        opensky_hint: Optional[Dict[str, Any]] = None
        fallback_match: Optional[Dict[str, Any]] = None

        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SIGINT/1.0)"}) as client:
            # 0. Free registration lookup first (adsb.fi / adsb.lol) – works well for OE-III
            for reg in (cfg.get("regs") or []):
                if not reg or not isinstance(reg, str):
                    continue
                ac_list_reg = await _fetch_adsb_by_registration(client, reg)
                if ac_list_reg:
                    ac = ac_list_reg[0]
                    if _match_target_aircraft(ac, cfg):
                        latest_adsbx = _ac_to_position(ac, "adsb_registration")
                        break
                await asyncio.sleep(0.2)

            # 0b. Free region scan (Vienna, Eastern Med, Gulf) if registration had no hit
            if not latest_adsbx:
                region_candidates = await _fetch_adsb_regions_for_target(client, cfg)
                if region_candidates:
                    latest_adsbx = _ac_to_position(region_candidates[0], "adsb_region")

            # 1a. ADSBexchange via RapidAPI – callsign first, then ICAO, then multi-region
            if ADSBEXCHANGE_RAPIDAPI_KEY and not latest_adsbx:
                try:
                    ac_list_rapid: List[Dict[str, Any]] = []
                    # Try by callsign (e.g. OEIII, AFG401, FORTE11) – RapidAPI /api/aircraft/call/{callsign}
                    for reg in (cfg.get("regs") or []):
                        if not reg or not isinstance(reg, str):
                            continue
                        cs_clean = (reg or "").replace("-", "").replace(" ", "").strip().upper()
                        if not cs_clean:
                            continue
                        ac_list_rapid = await _fetch_adsbexchange_rapidapi(client, callsign=cs_clean)
                        if ac_list_rapid:
                            candidates = [ac for ac in ac_list_rapid if _match_target_aircraft(ac, cfg)]
                            if candidates:
                                latest_adsbx = _ac_to_position(candidates[0], "adsbexchange_rapidapi")
                                break
                        await asyncio.sleep(0.2)
                    if not latest_adsbx and (cfg.get("hex") or "").strip():
                        ac_list_rapid = await _fetch_adsbexchange_rapidapi(client, icao=(cfg.get("hex") or "").strip())
                        if ac_list_rapid:
                            candidates = [ac for ac in ac_list_rapid if _match_target_aircraft(ac, cfg)]
                            if candidates:
                                latest_adsbx = _ac_to_position(candidates[0], "adsbexchange_rapidapi")
                    if not latest_adsbx:
                        for _label, lat, lon, dist in ADSB_REGIONS_OEIII:
                            ac_list_rapid = await _fetch_adsbexchange_rapidapi(client, lat=lat, lon=lon, dist_nm=min(100, dist))
                            if ac_list_rapid:
                                candidates = [ac for ac in ac_list_rapid if _match_target_aircraft(ac, cfg)]
                                if candidates:
                                    latest_adsbx = _ac_to_position(candidates[0], "adsbexchange_rapidapi")
                                    break
                except Exception as e:
                    logger.debug("SIGINT: ADSBexchange RapidAPI target fetch failed: %s", e)

            # 1b. ADSB-Exchange direct – multi-region
            if ADSBX_BASE_URL and ADSBX_API_KEY and not latest_adsbx:
                try:
                    for _label, lat, lon, dist in ADSB_REGIONS_OEIII:
                        url = f"{ADSBX_BASE_URL.rstrip('/')}/v2/lat/{lat}/lon/{lon}/dist/{min(3000, dist)}"
                        resp = await client.get(url, headers={"api-key": ADSBX_API_KEY}, timeout=15.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            ac_list = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                            if isinstance(ac_list, list):
                                candidates = [ac for ac in ac_list if _match_target_aircraft(ac, cfg)]
                                if candidates:
                                    latest_adsbx = _ac_to_position(candidates[0], "adsbx")
                                    break
                    if not latest_adsbx:
                        url = f"{ADSBX_BASE_URL.rstrip('/')}/v2/lat/35/lon/25/dist/3000"
                        resp = await client.get(url, headers={"api-key": ADSBX_API_KEY}, timeout=15.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            ac_list = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                            if isinstance(ac_list, list):
                                candidates = [ac for ac in ac_list if _match_target_aircraft(ac, cfg)]
                                if candidates:
                                    latest_adsbx = _ac_to_position(candidates[0], "adsbx")
                except Exception as e:
                    logger.debug("SIGINT: ADSB-Exchange target fetch failed: %s", e)

            # 2. OpenSky history (optional)
            if OPENSKY_USERNAME and OPENSKY_PASSWORD and (cfg.get("hex") or "").strip():
                try:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    from_ts = now_ts - 24 * 3600
                    resp = await client.get(
                        "https://opensky-network.org/api/flights/aircraft",
                        params={"icao24": (cfg.get("hex") or "").lower(), "begin": from_ts, "end": now_ts},
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

            # 3. Fallback: if still no position, use military list (rare for OE-III) or leave fallback_match None
            if not latest_adsbx:
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
        return run_async(_run())
    except Exception as e:
        logger.exception("SIGINT: get_target_aircraft failed for %s: %s", target, e)
        return {"target": target, "error": str(e)}


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_sigint(conflict: str) -> Dict[str, Any]:
    """Execute SIGINT tool chain: aircraft → vessels → conflict_reports → NOTAMs. Hormuz tankers are filled from Chokepoint (AISStream) in supervisor when AIRSTREAM_API_KEY is set."""
    from .iaea_tracker import fetch_notams

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            fut_air = executor.submit(get_military_aircraft)
            fut_reports = executor.submit(get_conflict_reports, conflict)
            fut_notams = executor.submit(lambda: fetch_notams(days=3, limit=15))
            # Track all configured target aircraft (OE-III + any from TARGET_AIRCRAFT_EXTRA)
            target_names = list(TARGET_AIRCRAFT.keys())
            fut_targets = [executor.submit(get_target_aircraft, name) for name in target_names]

            try:
                raw_aircraft = fut_air.result(timeout=40)
            except Exception as e:
                logger.exception("SIGINT: aircraft fetch failed: %s", e)
                raw_aircraft = [{"error": str(e)}]

            # Naval vessels: no source (VesselFinder removed)
            raw_ships: List[Dict[str, Any]] = []

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

            # Hormuz tankers: filled from Chokepoint (AISStream) in supervisor merge
            target_tracks_dict: Dict[str, Any] = {}
            for name, fut in zip(target_names, fut_targets):
                try:
                    target_tracks_dict[name] = fut.result(timeout=40)
                except Exception as e:
                    logger.debug("SIGINT: target aircraft %s tracking failed: %s", name, e)
                    target_tracks_dict[name] = {"target": name, "error": str(e)}
            target_track = target_tracks_dict

        aircraft = [
            a for a in (raw_aircraft or [])
            if isinstance(a, dict) and "error" not in a
        ]
        ships = [
            s for s in (raw_ships or [])
            if isinstance(s, dict) and "error" not in s
        ]

        reports = [
            r for r in (raw_reports or [])
            if isinstance(r, dict) and "error" not in r
        ]
        notams = (notam_result.get("notams") or []) if isinstance(notam_result, dict) else []

        base = 30.0
        base += min(40, sum(10 for a in aircraft if a.get("category") == "surveillance"))
        base += sum(8 for a in aircraft if a.get("category") == "tanker")
        base += sum(12 for a in aircraft if a.get("category") == "fighter")
        base += sum(6 for a in aircraft if a.get("category") == "transport")
        base += sum(8 for a in aircraft if a.get("category") == "iranian_gov")
        # Doomsday planes (E-6B, E-4B) = highest escalation signal
        doomsday_count = sum(1 for a in aircraft if a.get("category") == "doomsday")
        base += doomsday_count * 25
        base += min(25, len(ships) * 5)
        base += min(30, len(reports) * 8)
        score = max(0.0, min(100.0, base))

        alerts: List[str] = []
        if aircraft:
            by_cat: Dict[str, List] = {}
            for a in aircraft:
                by_cat.setdefault(a.get("category", "?"), []).append(a.get("flight", "?"))
            if "doomsday" in by_cat:
                alerts.append(
                    f"⚠ {len(by_cat['doomsday'])} DOOMSDAY/NUCLEAR C3 aircraft: "
                    f"{', '.join(by_cat['doomsday'][:5])} — highest escalation signal"
                )
            if "iranian_gov" in by_cat:
                alerts.append(
                    f"🇮🇷 {len(by_cat['iranian_gov'])} Iranian gov/IRGC aircraft: "
                    f"{', '.join(by_cat['iranian_gov'][:5])}"
                )
            for cat, flights in by_cat.items():
                if cat in ("doomsday", "iranian_gov"):
                    continue
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
            ("conflict_reports", reports),
            ("notams", notams),
        ):
            if data:
                sources_ok.append(name)
            else:
                sources_missing.append(name)
        for tname, tdata in (target_track if isinstance(target_track, dict) else {}).items():
            if isinstance(tdata, dict) and not tdata.get("error") and (
                tdata.get("adsbx") or tdata.get("adsbexchange_rapidapi") or tdata.get("fallback_sigint") or tdata.get("opensky")
            ):
                sources_ok.append(f"target_{tname}")
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

        # Hormuz tankers: merged from Chokepoint (AISStream) in supervisor when AIRSTREAM_API_KEY set
        hormuz_tankers: List[Dict[str, Any]] = []

        result = SigintResult(
            conflict=conflict,
            aircraft=aircraft,
            ships=ships,
            hormuz_tankers=hormuz_tankers,
            hormuz_tanker_count=len(hormuz_tankers),
            conflict_reports=reports,
            notams=notams,
            sigint_score=round(score, 1),
            alerts=alerts,
            summary=(
                f"SIGINT (rule-based): {len(aircraft)} aircraft, "
                f"{len(ships)} ships, {len(hormuz_tankers)} Hormuz tankers, "
                f"{len(reports)} reports, {len(notams)} NOTAMs. "
                f"Score {score:.0f}."
            ),
            score_confidence=score_confidence,
            target_tracks=target_track if isinstance(target_track, dict) else {},
        )
        out = result.model_dump(mode="json")
        duration_ms = int((time.perf_counter() - start) * 1000)
        source_results = [
            SourceResult(name="ADS-B", status="ok" if aircraft else "error", fetched_at=fetched_at, record_count=len(aircraft)),
            SourceResult(name="Conflict Reports", status="ok" if reports else "error", fetched_at=fetched_at, record_count=len(reports)),
            SourceResult(name="NOTAMs", status="ok" if notams else "error", fetched_at=fetched_at, record_count=len(notams)),
            SourceResult(name="Hormuz Tankers", status="ok" if hormuz_tankers else "error", fetched_at=fetched_at, record_count=len(hormuz_tankers)),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "sigint", sr)
        confidence = compute_confidence_from_sources(source_results) if source_results else score_confidence
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count >= len(source_results) * 0.8 else "recent" if ok_count >= len(source_results) * 0.5 else "stale" if ok_count > 0 else "unavailable"
        error_summary = f"{len(sources_missing)} source(s) missing" if sources_missing else None
        meta = AgentMetadata(
            agent="sigint",
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            sources=source_results,
            confidence=confidence,
            data_freshness=data_freshness,
            fallback_used=False,
            error_summary=error_summary,
        )
        out["_meta"] = meta.model_dump(mode="json")
        return out
    except Exception as e:
        logger.exception("SIGINT: rule-based pipeline failed for conflict '%s': %s", conflict, e)
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(
            agent="sigint",
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            sources=[],
            confidence=ScoreConfidence(level="low", sources_ok=[], sources_missing=["pipeline"]),
            data_freshness="unavailable",
            fallback_used=True,
            error_summary=str(e),
        )
        return {
            "conflict": conflict,
            "aircraft": [],
            "ships": [],
            "conflict_reports": [],
            "notams": [],
            "sigint_score": 30.0,
            "alerts": [],
            "summary": "SIGINT error: pipeline failed.",
            "_meta": meta.model_dump(mode="json"),
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


_SIGINT_TOOL_FNS = {
    "get_military_aircraft": get_military_aircraft,
    "get_naval_vessels": get_naval_vessels,
    "get_conflict_reports": get_conflict_reports,
}
_SIGINT_TOOL_SCHEMAS = [
    {"name": "get_military_aircraft", "description": "Fetch military aircraft in conflict regions via ADS-B.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_naval_vessels", "description": "Fetch naval vessels in conflict regions.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_conflict_reports", "description": "Fetch conflict intelligence reports from RSS feeds.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
]


def run_sigint_agent(conflict: str) -> Dict[str, Any]:
    return run_agent_with_fallback(
        conflict,
        rule_based_fn=_run_rule_based_sigint,
        system_prompt=SIGINT_SYSTEM,
        user_content_template="Monitor military movements for conflict: {conflict}",
        tool_fns=_SIGINT_TOOL_FNS,
        tool_schemas=_SIGINT_TOOL_SCHEMAS,
        max_rounds=6,
    )
