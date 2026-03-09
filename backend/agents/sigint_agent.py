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
import os
from typing import Any, Dict, List

import httpx
from .llm_factory import get_agent_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

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

@tool
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


@tool
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
        return [{"error": str(e)}]


@tool
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
        except Exception:
            pass
        return out[:80]

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []


@tool
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
        return [{"error": str(e)}]


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_sigint(conflict: str) -> Dict[str, Any]:
    """Execute SIGINT tool chain in fixed order: aircraft → vessels → spire_vessels (subagent) → conflict_reports. No LLM."""
    aircraft = [a for a in (get_military_aircraft.invoke({}) or []) if isinstance(a, dict) and "error" not in a]
    ships = [s for s in (get_naval_vessels.invoke({}) or []) if isinstance(s, dict) and "error" not in s]
    spire_ships = [s for s in (get_spire_vessels.invoke({}) or []) if isinstance(s, dict) and "error" not in s]
    seen_ship = {(s.get("name") or "").lower()[:40] or str(s.get("lat")) + "," + str(s.get("lon")) for s in ships}
    for s in spire_ships:
        key = (s.get("name") or "").lower()[:40] or str(s.get("lat")) + "," + str(s.get("lon"))
        if key not in seen_ship:
            seen_ship.add(key)
            ships.append(s)
    reports = [r for r in (get_conflict_reports.invoke({"conflict": conflict}) or []) if isinstance(r, dict) and "error" not in r]

    base = 30.0
    base += min(40, sum(10 for a in aircraft if a.get("category") == "surveillance"))
    base += sum(8 for a in aircraft if a.get("category") == "tanker")
    base += sum(12 for a in aircraft if a.get("category") == "fighter")
    base += min(25, len(ships) * 5)
    base += min(30, len(reports) * 8)
    score = max(0.0, min(100.0, base))

    alerts = []
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

    return {
        "conflict": conflict,
        "aircraft": aircraft,
        "ships": ships,
        "conflict_reports": reports,
        "sigint_score": round(score, 1),
        "alerts": alerts,
        "summary": f"SIGINT (rule-based): {len(aircraft)} aircraft, {len(ships)} ships, {len(reports)} reports. Score {score:.0f}.",
    }


# ── Agent ──────────────────────────────────────────────────────────────────

SIGINT_TOOLS = [get_military_aircraft, get_naval_vessels, get_spire_vessels, get_conflict_reports]

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

    model = get_agent_model(SIGINT_TOOLS)
    messages = [
        SystemMessage(content=SIGINT_SYSTEM),
        HumanMessage(content=f"Monitor military movements for conflict: {conflict}"),
    ]

    for _ in range(6):
        response = model.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            try:
                content = response.content
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                text = (content or "").strip()
                for p in ("```json", "```"):
                    if text.startswith(p):
                        text = text[len(p):].strip()
                if text.endswith("```"):
                    text = text[:-3].strip()
                result = json.loads(text)
                result["conflict"] = conflict
                return result
            except Exception:
                break

        for tc in response.tool_calls:
            tool_map = {t.name: t for t in SIGINT_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                result = tool_fn.invoke(tc.get("args", {}))
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    # Fallback: same fixed tool chain as rule-based mode
    return _run_rule_based_sigint(conflict)
