import re
import asyncio
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from ..config import USER_AGENT
from ..utils import run_async
from ..utils import parse_adsb_response, safe_float

logger = logging.getLogger(__name__)


def get_conflict_reports(conflict: str = "Iran") -> List[Dict[str, Any]]:
    """Fetch recent military/conflict reports from RSS sources."""
    conflict_keywords = {
        "iran": ["iran", "irgc", "tehran", "hormuz", "houthi", "yemen", "persian gulf", "hezbollah", "idf", "lebanon"],
        "ukraine": ["ukraine", "russia", "kyiv", "donbas"],
        "israel": ["israel", "gaza", "hamas", "hezbollah", "idf"],
        "taiwan": ["taiwan", "pla", "strait", "china"],
    }
    cl = conflict.lower()
    keywords = next((v for k, v in conflict_keywords.items() if k in cl), cl.split())

    async def _fetch():
        results: List[Dict[str, Any]] = []
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
                        results.append(
                            {
                                "title": title,
                                "date": date_m.group(1) if date_m else "",
                                "url": link_m.group(1) if link_m else "",
                                "source": feed_url.split("/")[2],
                            }
                        )
                except Exception:
                    continue
        return results[:10]

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


def get_naval_vessels(region: str = "Middle East") -> List[Dict[str, Any]]:
    """Naval vessels source placeholder (currently no external API configured)."""
    return []


ADSB_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}",
    "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}",
]
ADSB_MIL_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/mil",
    "https://api.adsb.lol/v2/mil",
]
ADSB_REGIONS = [("Persian Gulf", 26.0, 55.0, 400), ("Iraq/Iran", 33.0, 46.0, 400), ("Eastern Med", 33.0, 35.0, 350), ("Red Sea", 20.0, 40.0, 350)]
MILITARY_CALLSIGN_PREFIXES = ["RCH", "USAF", "NAVY", "DUKE", "REACH", "JAKE", "EVAC", "SAM", "HAVOC", "VIPER", "SKULL", "IRON", "DOOM", "GHOST", "ATLAS", "SPAR", "FORTE", "TACAMO", "NCHO"]
SURVEILLANCE_TYPES = ["RC-135", "E-3", "E-8", "P-8", "EP-3", "RQ-4", "MQ-9", "U-2", "E-2", "E-6", "RC12", "MC-12", "P-3", "E-7", "E7A", "E6B"]
TANKER_TYPES = ["KC-135", "KC-10", "KC-46", "KC130", "A330", "MRTT", "A310", "KC-30"]
FIGHTER_TYPES = ["F-16", "F-15", "F-35", "F/A-18", "FA18", "B-52", "B-2", "B1"]
TRANSPORT_TYPES = ["C-17", "C-130", "C-5", "C-40", "C-37", "C-32", "Il-76", "IL76", "An-124", "AN124", "747"]
DOOMSDAY_TYPES = ["E-6", "E6B", "E-4", "E4B"]
HIGH_PRIORITY_CALLSIGNS = ["FORTE", "TACAMO", "NCHO", "DARKSTAR", "GORDO"]
ADSB_REGISTRATION_URLS = ["https://opendata.adsb.fi/api/v2/registration/{reg}", "https://api.adsb.lol/v2/registration/{reg}"]
ADSB_TARGET_SCAN_REGIONS = [
    ("Vienna/Austria", 48.2, 16.4, 350),
    ("Eastern Med", 33.0, 35.0, 400),
    ("Persian Gulf", 26.0, 55.0, 450),
    ("Al Udeid/Qatar", 25.1, 51.3, 200),
    ("Al Dhafra/UAE", 24.2, 54.5, 200),
    ("Akrotiri/Cyprus", 34.6, 33.0, 250),
    ("Jordan corridor", 31.5, 36.5, 300),
    ("Northern Iraq", 36.0, 44.0, 300),
    ("Strait of Hormuz", 26.5, 56.3, 200),
    ("Tehran FIR", 35.7, 51.4, 400),
    ("Syria corridor", 34.5, 38.5, 300),
]
ADSB_REGIONS_OEIII = ADSB_TARGET_SCAN_REGIONS
ADSBX_BASE_URL = os.getenv("ADSBX_BASE_URL", "").rstrip("/") or None
ADSBX_API_KEY = (os.getenv("ADSBX_API_KEY") or "").strip() or None
ADSBEXCHANGE_RAPIDAPI_KEY = (os.getenv("ADSBEXCHANGE_RAPIDAPI_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip() or None
ADSBEXCHANGE_RAPIDAPI_HOST = (os.getenv("ADSBEXCHANGE_RAPIDAPI_HOST") or "adsbexchange-com1.p.rapidapi.com").strip()
OPENSKY_USERNAME = (os.getenv("OPENSKY_USERNAME") or "").strip() or None
OPENSKY_PASSWORD = (os.getenv("OPENSKY_PASSWORD") or "").strip() or None


def _target_aircraft_from_env() -> Dict[str, Dict[str, Any]]:
    targets: Dict[str, Dict[str, Any]] = {
        "OE-III": {"hex": (os.getenv("OEIII_HEX") or "").lower() or None, "regs": ["OE-III", "OEIII", "OE III"], "notes": "IAEA / diplomatic jet (Rafael Grossi)"},
        "EP-FAA": {"hex": (os.getenv("TARGET_EPFAA_HEX") or "").lower() or None, "regs": ["EP-FAA", "EPFAA"], "notes": "Qeshm Fars Air 747F"},
        "EP-FAB": {"hex": (os.getenv("TARGET_EPFAB_HEX") or "").lower() or None, "regs": ["EP-FAB", "EPFAB"], "notes": "Qeshm Fars Air 747F"},
        "EP-IGA": {"hex": (os.getenv("TARGET_EPIGA_HEX") or "").lower() or None, "regs": ["EP-IGA", "EPIGA"], "notes": "Iran government A340"},
        "EP-IGC": {"hex": (os.getenv("TARGET_EPIGC_HEX") or "").lower() or None, "regs": ["EP-IGC", "EPIGC"], "notes": "Iran government Falcon 900"},
    }
    targets["POUYA"] = {"hex": (os.getenv("TARGET_POUYA_HEX") or "").lower() or None, "regs": ["IRZ", "POUYA"], "notes": "Pouya Air Il-76"}
    extra = (os.getenv("TARGET_AIRCRAFT_EXTRA") or "").strip()
    for name in [x.strip().upper() for x in extra.split(",") if x.strip()]:
        if name in targets:
            continue
        hex_val = (os.getenv(f"TARGET_{name.replace('-', '_')}_HEX") or "").lower() or None
        targets[name] = {"hex": hex_val, "regs": [name, name.replace("-", "")], "notes": "Custom target"}
    return targets


TARGET_AIRCRAFT: Dict[str, Dict[str, Any]] = _target_aircraft_from_env()


def _adsbexchange_rapidapi_headers() -> Dict[str, str]:
    return {"X-RapidAPI-Key": ADSBEXCHANGE_RAPIDAPI_KEY or "", "X-RapidAPI-Host": ADSBEXCHANGE_RAPIDAPI_HOST, "User-Agent": USER_AGENT}


def _classify_aircraft(callsign: str, ac_type: str, reg: str = "") -> str | None:
    cs = (callsign or "").upper().strip()
    t = (ac_type or "").upper().strip()
    r = (reg or "").upper().strip()
    if any(x in t for x in DOOMSDAY_TYPES) or any(cs.startswith(p) for p in ("TACAMO", "NCHO")):
        return "doomsday"
    if any(x in t for x in FIGHTER_TYPES):
        return "fighter"
    if any(x in t for x in SURVEILLANCE_TYPES) or any(cs.startswith(p) for p in HIGH_PRIORITY_CALLSIGNS):
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


def _match_target_aircraft(ac: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
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
    return bool(callsign and any(cs in callsign for cs in regs))


async def _fetch_adsbexchange_rapidapi(client: httpx.AsyncClient, *, icao: str | None = None, callsign: str | None = None, lat: float | None = None, lon: float | None = None, dist_nm: int = 100) -> List[Dict[str, Any]]:
    if not ADSBEXCHANGE_RAPIDAPI_KEY:
        return []
    base = f"https://{ADSBEXCHANGE_RAPIDAPI_HOST}"
    headers = _adsbexchange_rapidapi_headers()
    try:
        if icao:
            resp = await client.get(f"{base}/api/aircraft/icao/{icao.strip().upper()}", headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                return ac if isinstance(ac, list) else ([ac] if isinstance(ac, dict) else [])
        elif callsign and callsign.strip():
            resp = await client.get(f"{base}/api/aircraft/call/{callsign.strip().upper()}", headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                return ac if isinstance(ac, list) else ([ac] if isinstance(ac, dict) else [])
        elif lat is not None and lon is not None:
            resp = await client.get(f"{base}/api/aircraft/lat/{lat}/lon/{lon}/dist/{min(100, max(1, int(dist_nm)))}", headers=headers, timeout=15.0)
            if resp.status_code == 200:
                return parse_adsb_response(resp.json())
    except Exception:
        return []
    return []


async def _fetch_adsb_by_registration(client: httpx.AsyncClient, reg: str) -> List[Dict[str, Any]]:
    reg_clean = (reg or "").replace("-", "").replace(" ", "").strip().upper()
    if not reg_clean:
        return []
    for tpl in ADSB_REGISTRATION_URLS:
        try:
            resp = await client.get(tpl.format(reg=reg_clean), timeout=12.0)
            if resp.status_code == 200:
                ac = parse_adsb_response(resp.json())
                if ac:
                    return ac
        except Exception:
            continue
    return []


def get_military_aircraft(region: str = "Middle East") -> List[Dict[str, Any]]:
    async def _fetch_mil_global(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
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

    async def _fetch_region(client: httpx.AsyncClient, lat: float, lon: float, dist: int) -> List[Dict[str, Any]]:
        for tpl in ADSB_ENDPOINTS:
            try:
                resp = await client.get(tpl.format(lat=lat, lon=lon, dist=dist), timeout=15.0)
                if resp.status_code == 200:
                    data = resp.json()
                    ac = data if isinstance(data, list) else data.get("ac", data.get("aircraft", []))
                    if isinstance(ac, list):
                        return ac
            except Exception:
                continue
        return []

    async def _run():
        results: List[Dict[str, Any]] = []
        seen_icao: set[str] = set()
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
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
                results.append({"flight": callsign or icao, "type": ac_type, "lat": lat, "lon": lon, "category": _classify_aircraft(callsign, ac_type) or "military", "source": "mil-global"})
            tasks = [_fetch_region(client, lat, lon, dist) for _, lat, lon, dist in ADSB_REGIONS]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)
            for (label, _, _, _), ac_list in zip(ADSB_REGIONS, all_results, strict=True):
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
                    lat = safe_float(ac.get("lat"))
                    lon = safe_float(ac.get("lon"))
                    if lat is None or lon is None:
                        continue
                    seen_icao.add(icao)
                    results.append({"flight": callsign or ac_type or icao, "type": ac_type, "lat": lat, "lon": lon, "category": cat, "region": label, "reg": reg or None})
        return results

    try:
        return run_async(_run())
    except Exception as e:
        return [{"error": str(e)}]


def get_target_aircraft(target: str = "OE-III") -> Dict[str, Any]:
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
        latest_adsbx: Dict[str, Any] | None = None
        opensky_hint: Dict[str, Any] | None = None
        fallback_match: Dict[str, Any] | None = None
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; SIGINT/1.0)"}) as client:
            for reg in cfg.get("regs") or []:
                ac_list_reg = await _fetch_adsb_by_registration(client, reg)
                if ac_list_reg and _match_target_aircraft(ac_list_reg[0], cfg):
                    latest_adsbx = _ac_to_position(ac_list_reg[0], "adsb_registration")
                    break
                await asyncio.sleep(0.2)
            if ADSBEXCHANGE_RAPIDAPI_KEY and not latest_adsbx:
                for reg in cfg.get("regs") or []:
                    cs_clean = (reg or "").replace("-", "").replace(" ", "").strip().upper()
                    if not cs_clean:
                        continue
                    rapid = await _fetch_adsbexchange_rapidapi(client, callsign=cs_clean)
                    cand = [ac for ac in rapid if _match_target_aircraft(ac, cfg)]
                    if cand:
                        latest_adsbx = _ac_to_position(cand[0], "adsbexchange_rapidapi")
                        break
            if OPENSKY_USERNAME and OPENSKY_PASSWORD and (cfg.get("hex") or "").strip():
                try:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    resp = await client.get(
                        "https://opensky-network.org/api/flights/aircraft",
                        params={"icao24": (cfg.get("hex") or "").lower(), "begin": now_ts - 24 * 3600, "end": now_ts},
                        auth=(OPENSKY_USERNAME, OPENSKY_PASSWORD),
                        timeout=20.0,
                    )
                    if resp.status_code == 200 and isinstance(resp.json(), list) and resp.json():
                        last = resp.json()[-1]
                        opensky_hint = {"last_callsign": last.get("callsign"), "last_origin": last.get("estDepartureAirport"), "last_destination": last.get("estArrivalAirport"), "last_time": last.get("lastSeen") or last.get("firstSeen")}
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    logger.debug("SIGINT: OpenSky lookup failed for %s: %s", target, exc)
            if not latest_adsbx:
                mil = get_military_aircraft() or []
                for ac in mil:
                    if _match_target_aircraft(ac, cfg):
                        fallback_match = {"flight": ac.get("flight"), "lat": ac.get("lat"), "lon": ac.get("lon"), "type": ac.get("type"), "category": ac.get("category"), "source": ac.get("source", "mil-global"), "position_source": "adsb"}
                        break
        result["adsbx"] = latest_adsbx
        result["opensky"] = opensky_hint
        result["fallback_sigint"] = fallback_match
        result["confidence"] = "high" if latest_adsbx else ("medium" if fallback_match or opensky_hint else "low")
        return result

    try:
        return run_async(_run())
    except Exception as e:
        return {"target": target, "error": str(e)}
