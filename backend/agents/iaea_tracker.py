"""
IAEA / OE-III Tracker – Multisensor-Fusion für Rafael Grossi / IAEO-Flugzeug (2026).

Säulen:
- ADS-B: OE-III per Registration + ICAO-Hex (440333), Boden-Modus, ORER-Erkennung.
- NOTAMs: Autorouter.aero / Eurocontrol EAD.
- IAEA-Press: RSS, Filter Grossi/DG.
- Flugplan-Status: optional IAEA_FLIGHTPLAN_STATUS_URL (IFPS/NMOC-Proxy).
- Telegram: optional IAEA_TELEGRAM_CHANNELS (Erbil/Kurdistan); t.me/s-Scraping ist fragil/rate-limited,
  für ernsthaftes Monitoring wäre Telethon/Pyrogram mit eigenem Account stabiler (technische Schuld).
Jede Fetch-Funktion liefert correlation_hint + confidence; _build_correlation_notes aggregiert nur.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import httpx

from .health_registry import get_health_registry
from .utils import (
    AgentMetadata,
    SourceResult,
    compute_confidence_from_sources,
    parse_adsb_response,
    run_async,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

# OE-III: österreichische Registration, IAEA DG Flugzeug
OEIII_REGISTRATION = "OE-III"
OEIII_CALLSIGN_VARIANTS = ("OE-III", "OEIII", "OE III")
# ICAO Hex für OE-III (Diplomatenjets oft auf kommerziellen Karten ausgeblendet → direkt tracken)
OEIII_ICAO_HEX = (os.getenv("OEIII_ICAO_HEX") or "440333").strip().upper()

# ORER Erbil International Airport (Referenz für „parked Erbil“)
ORER_LAT, ORER_LON = 36.2375, 43.9631
ORER_MAX_NM = 5.0

# ADS-B
ADSB_REGISTRATION_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/registration/{reg}",
    "https://api.adsb.lol/v2/registration/{reg}",
]
ADSB_HEX_ENDPOINTS = [
    "https://api.adsb.lol/v2/hex/{hex}",
    "https://opendata.adsb.fi/api/v2/hex/{hex}",
]
ADSB_REGIONS_OEIII = [
    ("Vienna/Austria", 48.2, 16.4, 350),
    ("Eastern Med", 33.0, 35.0, 400),
    ("Erbil/ORER", ORER_LAT, ORER_LON, 80),
    ("Persian Gulf", 26.0, 55.0, 450),
]
ADSB_LATLON_TEMPLATE = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}"

# ADSBexchange RapidAPI (optional fallback when free sources return no OE-III)
ADSBEXCHANGE_RAPIDAPI_KEY = (os.getenv("ADSBEXCHANGE_RAPIDAPI_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip() or None
ADSBEXCHANGE_RAPIDAPI_HOST = (os.getenv("ADSBEXCHANGE_RAPIDAPI_HOST") or "adsbexchange-com1.p.rapidapi.com").strip()

# IAEA Press
IAEA_FEEDS = [
    "https://www.iaea.org/newscenter/news/feed",
    "https://www.iaea.org/newscenter/pressreleases/feed",
]
GROSSI_KEYWORDS = ("grossi", "director general", "dg grossi", "iaea chief", "rafael grossi")

# NOTAM
NOTAM_API_URL = os.getenv("NOTAM_API_URL", "https://api.autorouter.aero/v1.0/notam").strip()
NOTAM_API_KEY = os.getenv("NOTAM_API_KEY", "").strip()
NOTAM_ICAO_DEFAULT = ["EDDS", "LOWW", "OIIE", "ORER"]

# Flugplan-Status (optional: eigener Proxy oder manuell gepflegter JSON)
IAEA_FLIGHTPLAN_STATUS_URL = os.getenv("IAEA_FLIGHTPLAN_STATUS_URL", "").strip()
IAEA_FLIGHTPLAN_STATUS = os.getenv("IAEA_FLIGHTPLAN_STATUS", "").strip().lower()
IAEA_FLIGHTPLAN_LAST_UPDATED_ISO = os.getenv("IAEA_FLIGHTPLAN_LAST_UPDATED_ISO", "").strip() or None

# Telegram: Erbil/Kurdistan/IAEA-spezifische Kanäle (kommagetrennt)
# Hinweis: t.me/s-Scraping ist fragil und rate-limited; für ernsthaftes Monitoring Telethon/Pyrogram empfohlen.
IAEA_TELEGRAM_CHANNELS_RAW = os.getenv("IAEA_TELEGRAM_CHANNELS", "").strip()
IAEA_TELEGRAM_CHANNELS = [c.strip() for c in IAEA_TELEGRAM_CHANNELS_RAW.split(",") if c.strip()]
IAEA_TELEGRAM_KEYWORDS = (
    "erbil",
    "kurdistan",
    "bashmakh",
    "haji omeran",
    "iaea",
    "grossi",
    "orer",
    "convoy",
    "konvoi",
    "checkpoint",
    "oe-iii",
    "oeiii",
)

# Cache: Deduplication für Press/Telegram (TTL Minuten)
IAEA_CACHE_TTL_MINUTES = max(1, min(120, int(os.getenv("IAEA_CACHE_TTL_MINUTES", "15"))))
_seen_press_ids: Dict[str, float] = {}
_seen_telegram_ids: Dict[str, float] = {}
_cache_ttl_seconds = IAEA_CACHE_TTL_MINUTES * 60


def _normalize_reg_callsign(s: Optional[str]) -> str:
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", "", s.strip().upper())


def _is_oeiii(ac: Dict[str, Any]) -> bool:
    """Prüft, ob ein Flugzeug-Objekt OE-III (IAEA DG) ist (Registration oder Hex)."""
    reg = _normalize_reg_callsign(ac.get("r") or ac.get("registration") or "")
    flight = _normalize_reg_callsign(ac.get("flight") or ac.get("callsign") or "")
    hex_val = str(ac.get("hex") or "").strip().upper()
    if hex_val and hex_val == OEIII_ICAO_HEX:
        return True
    if reg and "OEIII" in reg.replace("-", ""):
        return True
    if flight and any(v.replace("-", "") in flight for v in OEIII_CALLSIGN_VARIANTS):
        return True
    return False


def _is_near_airport(
    lat: Optional[float],
    lon: Optional[float],
    ref_lat: float = ORER_LAT,
    ref_lon: float = ORER_LON,
    max_nm: float = ORER_MAX_NM,
) -> bool:
    """Grobe Prüfung: Position innerhalb max_nm (nautische Meilen) des Referenzpunkts."""
    if lat is None or lon is None:
        return False
    # Vereinfachte Distanz (ausreichend für kleine max_nm)
    dlat = (lat - ref_lat) * 60.0
    dlon = (lon - ref_lon) * 60.0 * 0.9  # cos(36°)
    return (dlat * dlat + dlon * dlon) ** 0.5 <= max_nm


async def _fetch_adsb_by_registration(client: httpx.AsyncClient, reg: str) -> List[Dict[str, Any]]:
    reg_clean = reg.replace("-", "").strip()
    if not reg_clean:
        return []
    for tpl in ADSB_REGISTRATION_ENDPOINTS:
        url = tpl.format(reg=reg_clean)
        try:
            resp = await client.get(url, timeout=12.0)
            if resp.status_code != 200:
                continue
            data = resp.json()
            ac = data if isinstance(data, list) else (data.get("ac") or data.get("aircraft") or [])
            if isinstance(ac, list) and ac:
                return ac
        except Exception:
            continue
    return []


async def _fetch_adsb_by_hex(client: httpx.AsyncClient, hex_code: str) -> List[Dict[str, Any]]:
    """Direkte Abfrage nach ICAO-Hex (Diplomatenjets oft ausgeblendet auf FR24 etc.)."""
    hex_clean = hex_code.replace("0x", "").strip().lower()
    if not hex_clean:
        return []
    for tpl in ADSB_HEX_ENDPOINTS:
        url = tpl.format(hex=hex_clean)
        try:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code != 200:
                continue
            data = resp.json()
            ac = data if isinstance(data, list) else (data.get("ac") or data.get("aircraft") or [])
            if isinstance(ac, list):
                return ac
        except Exception:
            continue
    return []


async def _fetch_adsb_region(client: httpx.AsyncClient, lat: float, lon: float, dist: int) -> List[Dict[str, Any]]:
    url = ADSB_LATLON_TEMPLATE.format(lat=lat, lon=lon, dist=min(500, dist))
    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code != 200:
            return []
        data = resp.json()
        ac = data if isinstance(data, list) else (data.get("ac") or data.get("aircraft") or [])
        if not isinstance(ac, list):
            return []
        return [a for a in ac if _is_oeiii(a)]
    except Exception:
        return []


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
    Fetch aircraft from ADSBexchange via RapidAPI (same endpoints as SIGINT).
    One of: icao, callsign, or (lat, lon, dist_nm). Max 100 nm for region queries.
    """
    if not ADSBEXCHANGE_RAPIDAPI_KEY:
        return []
    base = f"https://{ADSBEXCHANGE_RAPIDAPI_HOST}"
    headers = {
        "X-RapidAPI-Key": ADSBEXCHANGE_RAPIDAPI_KEY,
        "X-RapidAPI-Host": ADSBEXCHANGE_RAPIDAPI_HOST,
        "User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)",
    }
    ac_list: List[Dict[str, Any]] = []
    try:
        if icao and icao.strip():
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
        logger.debug("IAEA: ADSBexchange RapidAPI fetch failed: %s", e)
    return ac_list


def _normalize_aircraft(ac: Dict[str, Any], region: str = "") -> Dict[str, Any]:
    lat = ac.get("lat")
    lon = ac.get("lon")
    try:
        lat_f = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat_f = None
    try:
        lon_f = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon_f = None
    gnd = ac.get("gnd") if "gnd" in ac else ac.get("on_ground")
    if gnd is None and (ac.get("alt_baro") is None or ac.get("alt_baro") == "ground"):
        gnd = True
    location_interpretation = None
    if gnd and lat_f is not None and lon_f is not None and _is_near_airport(lat_f, lon_f):
        location_interpretation = "parked_erbil"
    return {
        "hex": str(ac.get("hex") or "").strip().upper(),
        "flight": str(ac.get("flight") or ac.get("callsign") or "").strip(),
        "registration": str(ac.get("r") or ac.get("registration") or "").strip(),
        "type": str(ac.get("t") or ac.get("type") or "").strip(),
        "lat": lat_f,
        "lon": lon_f,
        "alt_baro": ac.get("alt_baro") or ac.get("altitude"),
        "on_ground": bool(gnd) if gnd is not None else None,
        "region": region,
        "seen_at": ac.get("seen") or ac.get("timestamp"),
        "location_interpretation": location_interpretation,
    }


def fetch_adsb_oeiii() -> Dict[str, Any]:
    """
    ADS-B für OE-III: Registration, Hex-Lookup, Region-Scans.
    Liefert correlation_hint + confidence (high bei Hex+Boden+ORER).
    """

    async def _run() -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        seen_hex: set = set()
        adsbexchange_fallback_used = False
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)"}
        async with httpx.AsyncClient(headers=headers) as client:
            # 1) Hex-Direktabfrage
            hex_ac = await _fetch_adsb_by_hex(client, OEIII_ICAO_HEX)
            for ac in hex_ac:
                icao = str(ac.get("hex") or "").strip().upper()
                if icao and icao not in seen_hex:
                    seen_hex.add(icao)
                    results.append(_normalize_aircraft(ac, "hex"))
            # 2) Registration
            by_reg = await _fetch_adsb_by_registration(client, OEIII_REGISTRATION)
            for ac in by_reg:
                icao = str(ac.get("hex") or "").strip().upper()
                if icao and icao not in seen_hex:
                    seen_hex.add(icao)
                    results.append(_normalize_aircraft(ac, "registration"))
            # 3) Region-Scans
            for label, lat, lon, dist in ADSB_REGIONS_OEIII:
                regional = await _fetch_adsb_region(client, lat, lon, dist)
                for ac in regional:
                    icao = str(ac.get("hex") or "").strip().upper()
                    if icao and icao not in seen_hex:
                        seen_hex.add(icao)
                        results.append(_normalize_aircraft(ac, label))
                await asyncio.sleep(0.3)

            # 4) ADSBexchange RapidAPI fallback when free sources returned nothing
            if not results and ADSBEXCHANGE_RAPIDAPI_KEY:
                for ac in await _fetch_adsbexchange_rapidapi(client, icao=OEIII_ICAO_HEX):
                    icao = str(ac.get("hex") or "").strip().upper()
                    if icao and icao not in seen_hex and _is_oeiii(ac):
                        seen_hex.add(icao)
                        results.append(_normalize_aircraft(ac, "hex (ADSBexchange)"))
                        adsbexchange_fallback_used = True
                await asyncio.sleep(0.2)
                if not results:
                    for cs in ("OEIII", "OE-III"):
                        for ac in await _fetch_adsbexchange_rapidapi(client, callsign=cs):
                            icao = str(ac.get("hex") or "").strip().upper()
                            if icao and icao not in seen_hex and _is_oeiii(ac):
                                seen_hex.add(icao)
                                results.append(_normalize_aircraft(ac, "registration (ADSBexchange)"))
                                adsbexchange_fallback_used = True
                                break
                        if results:
                            break
                        await asyncio.sleep(0.2)
                if not results:
                    for label, lat, lon, dist in ADSB_REGIONS_OEIII:
                        regional = await _fetch_adsbexchange_rapidapi(client, lat=lat, lon=lon, dist_nm=min(100, dist))
                        for ac in regional:
                            if not _is_oeiii(ac):
                                continue
                            icao = str(ac.get("hex") or "").strip().upper()
                            if icao and icao not in seen_hex:
                                seen_hex.add(icao)
                                results.append(_normalize_aircraft(ac, f"{label} (ADSBexchange)"))
                                adsbexchange_fallback_used = True
                        await asyncio.sleep(0.2)

        # correlation_hint + confidence
        if not results:
            hint = "OE-III is currently not visible in ADS-B (on ground out of coverage or transponder off)."
            confidence = "low"
        else:
            ac0 = results[0]
            on_ground = ac0.get("on_ground")
            loc = ac0.get("location_interpretation")
            if on_ground and loc == "parked_erbil":
                hint = f"OE-III on ground in Erbil (hex {OEIII_ICAO_HEX} confirmed)."
                confidence = "high"
            elif on_ground:
                hint = f"OE-III reported on ground ({len(results)} source(s), hex {OEIII_ICAO_HEX})."
                confidence = "high"
            else:
                hint = f"OE-III airborne: {len(results)} position(s) via ADS-B."
                confidence = "high"
        return {
            "registration": OEIII_REGISTRATION,
            "aircraft": results,
            "count": len(results),
            "source": "adsb",
            "adsbexchange_fallback_used": adsbexchange_fallback_used,
            "correlation_hint": hint,
            "confidence": confidence,
        }

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception("ADS-B fetch failed")
        return {
            "registration": OEIII_REGISTRATION,
            "aircraft": [],
            "count": 0,
            "source": "adsb",
            "adsbexchange_fallback_used": False,
            "error": str(e),
            "correlation_hint": f"ADS-B: request failed ({e}).",
            "confidence": "low",
        }


def fetch_notams(
    days: int = 3,
    icao_locations: Optional[List[str]] = None,
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """NOTAMs für ICAO-Plätze. Liefert correlation_hint + confidence."""
    locations = (icao_locations or NOTAM_ICAO_DEFAULT)[:20]
    out: List[Dict[str, Any]] = []
    if not NOTAM_API_URL:
        logger.info(
            "NOTAMs: no API URL. Set NOTAM_API_URL in backend/.env (e.g. https://api.autorouter.aero/v1.0/notam)."
        )
        return {
            "notams": [],
            "count": 0,
            "source": "notam",
            "correlation_hint": "NOTAM: no API URL configured.",
            "confidence": "low",
        }

    is_autorouter = "autorouter.aero" in NOTAM_API_URL
    if is_autorouter and not NOTAM_API_KEY:
        logger.debug(
            "NOTAMs: NOTAM_API_KEY not set. Autorouter.aero requires an API key. Add NOTAM_API_KEY to backend/.env."
        )

    async def _get() -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params: Dict[str, Any] = {}
            if is_autorouter:
                params["itemas"] = json.dumps(locations)
                params["offset"] = offset
                params["limit"] = min(100, max(1, limit))
                if NOTAM_API_KEY:
                    params["api_key"] = NOTAM_API_KEY
            else:
                params["days"] = days
                if NOTAM_API_KEY:
                    params["api_key"] = NOTAM_API_KEY
                if locations:
                    params["locations"] = ",".join(locations)
            try:
                resp = await client.get(NOTAM_API_URL, params=params)
                if resp.status_code in (401, 403) and is_autorouter and not NOTAM_API_KEY:
                    logger.info(
                        "NOTAMs: autorouter.aero requires API key (HTTP %s). Set NOTAM_API_KEY in backend/.env. "
                        "Trying FAA NOTAM fallback.",
                        resp.status_code,
                    )
                    return await _faa_notam_fallback(client, locations)
                if resp.status_code != 200:
                    try:
                        err_body = (resp.text or "")[:300]
                    except Exception:
                        err_body = ""
                    logger.warning(
                        "NOTAMs API returned HTTP %s. Check NOTAM_API_URL and NOTAM_API_KEY. %s",
                        resp.status_code,
                        err_body,
                    )
                    return []
                data = resp.json()
                if is_autorouter and isinstance(data, dict):
                    return data.get("rows") or []
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("notams") or data.get("items") or data.get("rows") or []
            except Exception as e:
                logger.warning("NOTAMs request failed: %s. Check NOTAM_API_URL and network.", e)
            return []

    async def _faa_notam_fallback(client: httpx.AsyncClient, locs: list) -> List[Dict[str, Any]]:
        """Fallback: try FAA NOTAM API (requires client_id + client_secret) or return synthetic entry."""
        faa_key = os.getenv("FAA_NOTAM_API_KEY", "").strip()
        if faa_key:
            try:
                resp = await client.get(
                    "https://external-api.faa.gov/notamapi/v1/notams",
                    params={"locationIdent": ",".join(locs[:4])},
                    headers={"client_id": faa_key},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("items") or data.get("notamList") or (data if isinstance(data, list) else [])
            except Exception:
                pass
        return [
            {
                "id": "FALLBACK",
                "text": f"NOTAM data unavailable – set NOTAM_API_KEY (autorouter.aero) in backend/.env for live data. Locations: {', '.join(locs)}",
                "effective": None,
                "expiry": None,
                "location": ",".join(locs),
            }
        ]

    try:
        out = run_async(_get())
    except Exception as e:
        out = []
        logger.warning("NOTAM fetch failed: %s", e)

    notams: List[Dict[str, Any]] = []
    for n in (out or [])[:100]:
        if not isinstance(n, dict):
            notams.append({"id": "", "text": str(n), "effective": None, "expiry": None, "location": ""})
            continue
        if is_autorouter:
            itema = n.get("itema") or []
            location = ",".join(itema) if isinstance(itema, list) else str(itema)
            notams.append(
                {
                    "id": str(n.get("id") or n.get("nof") or ""),
                    "text": (n.get("iteme") or n.get("itemd") or "").strip() or str(n.get("traffic") or ""),
                    "effective": n.get("startvalidity"),
                    "expiry": n.get("endvalidity"),
                    "location": location,
                }
            )
        else:
            notams.append(
                {
                    "id": str(n.get("id") or n.get("notam_id") or ""),
                    "text": (n.get("text") or n.get("raw") or n.get("summary") or "").strip(),
                    "effective": n.get("effective") or n.get("start") or n.get("startDate"),
                    "expiry": n.get("expiry") or n.get("end") or n.get("endDate"),
                    "location": n.get("location") or n.get("traffic") or "",
                }
            )

    hint = (
        f"{len(notams)} NOTAM(s) in selected period; potential airspace constraints for DG travel."
        if notams
        else "No NOTAMs retrieved."
    )
    return {
        "notams": notams,
        "count": len(notams),
        "source": "notam",
        "correlation_hint": hint,
        "confidence": "medium",
    }


def fetch_iaea_flight_plan_status() -> Dict[str, Any]:
    """
    Optionaler Flugplan-Status (IFPS/NMOC-Proxy). Wenn IAEA_FLIGHTPLAN_STATUS_URL gesetzt:
    GET liefert z.B. {"status": "no_new_request"|"cancelled"|"unknown", "last_updated_iso": "..."}.
    """
    out: Dict[str, Any] = {
        "status": "unknown",
        "last_updated_iso": None,
        "source": "flight_plan",
        "correlation_hint": "Flight plan status not configured.",
        "confidence": "low",
    }
    if not IAEA_FLIGHTPLAN_STATUS_URL and IAEA_FLIGHTPLAN_STATUS:
        out["status"] = IAEA_FLIGHTPLAN_STATUS
        out["last_updated_iso"] = IAEA_FLIGHTPLAN_LAST_UPDATED_ISO
        s = out["status"]
        if s == "no_new_request":
            out["correlation_hint"] = "Flight plan: no new request; aircraft likely parked (no new slot)."
            out["confidence"] = "medium"
        elif s == "cancelled":
            out["correlation_hint"] = "Flight plan: cancelled (CNL); slot not activated."
            out["confidence"] = "medium"
        else:
            out["correlation_hint"] = f"Flight plan status: {s}."
            out["confidence"] = "low"
        return out

    if not IAEA_FLIGHTPLAN_STATUS_URL:
        out["correlation_hint"] = "Flight plan status not configured."
        return out

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                IAEA_FLIGHTPLAN_STATUS_URL,
                headers={"User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)"},
            )
            if resp.status_code != 200:
                out["correlation_hint"] = "Flight plan: request failed."
                out["error"] = f"HTTP {resp.status_code}"
                return out
            data = resp.json() if resp.text else {}
            if isinstance(data, dict):
                out["status"] = (data.get("status") or "unknown").lower()
                out["last_updated_iso"] = data.get("last_updated_iso")
                s = out["status"]
                if s == "no_new_request":
                    out["correlation_hint"] = "Flight plan: no new request; aircraft likely parked (no new slot)."
                    out["confidence"] = "medium"
                elif s == "cancelled":
                    out["correlation_hint"] = "Flight plan: cancelled (CNL); slot not activated."
                    out["confidence"] = "medium"
                else:
                    out["correlation_hint"] = f"Flight plan status: {s}."
                    out["confidence"] = "low"
    except Exception as e:
        logger.warning("Flight plan status fetch failed: %s", e)
        out["correlation_hint"] = "Flight plan: request failed."
        out["error"] = str(e)
    return out


def _press_cache_key(item: Dict[str, Any]) -> str:
    return (item.get("link") or "") + "|" + (item.get("published") or "")


def _is_cached(id_key: str, cache: Dict[str, float], ttl_seconds: float) -> bool:
    now = time.time()
    if id_key in cache:
        if now - cache[id_key] < ttl_seconds:
            return True
        del cache[id_key]
    return False


def _add_to_cache(id_key: str, cache: Dict[str, float]) -> None:
    cache[id_key] = time.time()
    # Grobes TTL-Cleanup: alte Einträge entfernen
    cutoff = time.time() - _cache_ttl_seconds
    to_del = [k for k, v in cache.items() if v < cutoff]
    for k in to_del:
        del cache[k]


def fetch_iaea_press_releases(days: int = 14) -> Dict[str, Any]:
    """
    IAEA-Pressemitteilungen/News (RSS), Filter Grossi/DG. Mit Cache: bereits gesehene
    Posts werden nicht erneut als „neu“ gezählt (TTL IAEA_CACHE_TTL_MINUTES).
    """
    items: List[Dict[str, Any]] = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=timezone.utc)

    for feed_url in IAEA_FEEDS:
        try:
            parsed = feedparser.parse(
                feed_url,
                request_headers={"User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)"},
            )
            for entry in getattr(parsed, "entries", [])[:50]:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                link = entry.get("link") or ""
                published = entry.get("published") or entry.get("updated")
                try:
                    if getattr(entry, "published_parsed", None):
                        from time import mktime

                        pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                    else:
                        pub_dt = cutoff
                except Exception:
                    pub_dt = cutoff
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                text = f"{title} {summary}".lower()
                if not any(kw in text for kw in GROSSI_KEYWORDS):
                    continue
                item = {
                    "title": title[:500],
                    "link": link,
                    "published": published,
                    "summary": (summary[:1000] if summary else ""),
                }
                cache_key = _press_cache_key(item)
                if _is_cached(cache_key, _seen_press_ids, _cache_ttl_seconds):
                    continue
                _add_to_cache(cache_key, _seen_press_ids)
                items.append(item)
        except Exception:
            continue

    hint = f"{len(items)} IAEA press/news items related to Rafael Grossi (last {days} days, new within TTL)."
    confidence = "medium" if items else "low"
    return {
        "items": items,
        "count": len(items),
        "source": "iaea_press",
        "correlation_hint": hint,
        "confidence": confidence,
    }


def fetch_iaea_telegram_signals() -> Dict[str, Any]:
    """
    Telegram-Posts aus IAEA-spezifischen Kanälen (Erbil/Kurdistan). Env: IAEA_TELEGRAM_CHANNELS.
    Technische Schuld: t.me/s-Scraping ist fragil und rate-limited; für ernsthaftes Monitoring
    wäre ein Telethon-/Pyrogram-Client mit eigenem Account stabiler. Für MVP reicht Web-Scrape.
    """
    out: Dict[str, Any] = {
        "posts": [],
        "count": 0,
        "source": "iaea_telegram",
        "correlation_hint": "Telegram (IAEA): no channels configured.",
        "confidence": "low",
    }
    if not IAEA_TELEGRAM_CHANNELS:
        return out

    TELEGRAM_MESSAGE_PATTERNS = [
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*</div>',
        r'class="tgme_widget_message_text"[^>]*>(.*?)</div>',
        r"<div[^>]+js-message-text[^>]*>(.*?)</div>",
    ]

    def _extract(html: str) -> List[str]:
        for pattern in TELEGRAM_MESSAGE_PATTERNS:
            messages = re.findall(pattern, html, re.DOTALL)
            if messages:
                return [re.sub(r"<[^>]+>", "", m).strip() for m in messages]
        og = re.findall(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        if og:
            return [re.sub(r"<[^>]+>", "", d).strip() for d in og if d.strip()]
        return []

    async def _fetch_one(client: httpx.AsyncClient, channel: str) -> List[Dict[str, Any]]:
        try:
            url = f"https://t.me/s/{channel}"
            resp = await client.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return []
            texts = _extract(resp.text)
            results = []
            for text in (texts or [])[:15]:
                if not text or len(text) < 15:
                    continue
                tlower = text.lower()
                if not any(kw in tlower for kw in IAEA_TELEGRAM_KEYWORDS):
                    continue
                results.append(
                    {
                        "source": f"telegram:{channel}",
                        "text": text[:300],
                        "platform": "telegram",
                    }
                )
            return results
        except Exception:
            return []

    try:

        async def _run() -> List[Dict[str, Any]]:
            async with httpx.AsyncClient() as client:
                tasks = [_fetch_one(client, ch) for ch in IAEA_TELEGRAM_CHANNELS]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                posts = []
                for r in results:
                    if isinstance(r, list):
                        posts.extend(r)
                return posts

        all_posts = run_async(_run())
    except Exception as e:
        logger.warning("IAEA Telegram fetch failed: %s", e)
        out["error"] = str(e)
        out["correlation_hint"] = "Telegram (IAEA): request failed."
        return out

    # Cache: gesehene Post-IDs (source + text_hash) mit TTL
    seen = set()
    deduped = []
    for p in all_posts:
        if not isinstance(p, dict):
            continue
        key = (p.get("source") or "") + "|" + (p.get("text", "")[:200] or "")
        if key in seen:
            continue
        if _is_cached(key, _seen_telegram_ids, _cache_ttl_seconds):
            seen.add(key)
            continue
        _add_to_cache(key, _seen_telegram_ids)
        seen.add(key)
        deduped.append(p)

    out["posts"] = deduped
    out["count"] = len(deduped)
    if deduped:
        out["correlation_hint"] = (
            f"{len(deduped)} Telegram signals (Erbil/Kurdistan/IAEA); convoy/checkpoint activity possible."
        )
        out["confidence"] = "medium"
    else:
        out["correlation_hint"] = "Telegram (IAEA): no matching posts in configured channels."
    return out


def _build_correlation_notes(
    adsb: Dict[str, Any],
    notam: Dict[str, Any],
    flight_plan: Dict[str, Any],
    press: Dict[str, Any],
    telegram: Dict[str, Any],
) -> Tuple[List[Dict[str, str]], str]:
    """
    Aggregiert nur die correlation_hint + confidence aus allen Säulen.
    Keine eigene Korrelationslogik – jede Fetch-Funktion liefert ihren Hint.
    """
    hints_with_conf: List[Dict[str, str]] = []
    for _name, data in [
        ("ADS-B", adsb),
        ("NOTAM", notam),
        ("Flugplan", flight_plan),
        ("IAEA Press", press),
        ("Telegram", telegram),
    ]:
        if not isinstance(data, dict):
            continue
        hint = (data.get("correlation_hint") or "").strip()
        conf = (data.get("confidence") or "low").lower()
        if hint:
            hints_with_conf.append({"hint": hint, "confidence": conf})
    summary = " | ".join(h["hint"] for h in hints_with_conf) if hints_with_conf else "No correlation data."
    return hints_with_conf, summary


async def _generate_haiku_summary_iaea(result: Dict[str, Any]) -> Optional[str]:
    """Optional 3-4 sentence sensor-fusion narrative via haiku_service.analyst_summary."""
    try:
        import json

        from services.haiku_service import analyst_summary

        oe = result.get("oeiii_adsb") or {}
        press = result.get("iaea_press_grossi") or {}
        compact = {
            "adsb_count": oe.get("count", 0),
            "adsb_hint": oe.get("correlation_hint"),
            "flight_plan_status": (result.get("flight_plan_status") or {}).get("status"),
            "press_count": press.get("count", 0),
            "telegram_count": (result.get("iaea_telegram_signals") or {}).get("count", 0),
            "correlation_notes": result.get("correlation_notes"),
        }
        data = json.dumps(compact, indent=2)
        system = (
            "You are an IAEA/OSINT analyst. Summarize the following OE-III (IAEA aircraft) multi-sensor "
            "fusion data in 3-4 sentences: ADS-B sightings, NOTAM, flight plan status, IAEA press, "
            "Telegram. Give a concise assessment (e.g. operational status, visibility constraints, recent coverage). "
            "Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=300)
        return out.strip() if out else None
    except Exception:
        return None


def correlate_iaea_tracker(
    adsb_result: Optional[Dict[str, Any]] = None,
    notam_result: Optional[Dict[str, Any]] = None,
    flight_plan_result: Optional[Dict[str, Any]] = None,
    press_result: Optional[Dict[str, Any]] = None,
    telegram_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Korreliert alle Säulen; erwartet dass jede ihr correlation_hint + confidence liefert.
    _build_correlation_notes aggregiert nur.
    """
    adsb = adsb_result or {}
    notam = notam_result or {}
    flight_plan = flight_plan_result or {}
    press = press_result or {}
    telegram = telegram_result or {}

    correlation_notes, summary = _build_correlation_notes(adsb, notam, flight_plan, press, telegram)

    return {
        "oeiii_adsb": {
            "registration": OEIII_REGISTRATION,
            "aircraft": adsb.get("aircraft") or [],
            "count": adsb.get("count", 0),
            "correlation_hint": adsb.get("correlation_hint"),
            "confidence": adsb.get("confidence"),
        },
        "notams": {
            "notams": notam.get("notams") or [],
            "count": notam.get("count", 0),
            "correlation_hint": notam.get("correlation_hint"),
            "confidence": notam.get("confidence"),
        },
        "flight_plan_status": {
            "status": flight_plan.get("status", "unknown"),
            "last_updated_iso": flight_plan.get("last_updated_iso"),
            "correlation_hint": flight_plan.get("correlation_hint"),
            "confidence": flight_plan.get("confidence"),
        },
        "iaea_press_grossi": {
            "items": press.get("items") or [],
            "count": press.get("count", 0),
            "correlation_hint": press.get("correlation_hint"),
            "confidence": press.get("confidence"),
        },
        "iaea_telegram_signals": {
            "posts": telegram.get("posts") or [],
            "count": telegram.get("count", 0),
            "correlation_hint": telegram.get("correlation_hint"),
            "confidence": telegram.get("confidence"),
        },
        "ground_ops_signals": None,  # Optional später: Rundeep/Wallet-Aktivität Cross-Check
        "correlation_notes": correlation_notes,
        "summary": summary,
    }


def run_iaea_tracker() -> Dict[str, Any]:
    """
    Führt alle Fetches parallel aus (asyncio.gather mit return_exceptions=True).
    Bei Fehlern: Fallback-Dict mit correlation_hint/confidence, kein Crash.
    Caching für Press/Telegram über TTL; Korrelation nur Aggregation der Hints.
    """

    def _safe_fetch(name: str, fn, *args, **kwargs) -> Dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning("%s fetch failed: %s", name, e)
            return {
                "correlation_hint": f"{name}: request failed.",
                "confidence": "low",
                "error": str(e),
            }

    async def _run_all() -> Dict[str, Any]:
        loop = asyncio.get_event_loop()

        # Fetches die sync sind im Executor; Flugplan/Telegram/Press sync, ADS-B/NOTAM haben ggf. schon async
        def run_adsb():
            return _safe_fetch("ADS-B", fetch_adsb_oeiii)

        def run_notams():
            return _safe_fetch("NOTAM", fetch_notams, 3)

        def run_fp():
            return _safe_fetch("Flight plan", fetch_iaea_flight_plan_status)

        def run_press():
            return _safe_fetch("IAEA Press", fetch_iaea_press_releases, 14)

        def run_telegram():
            return _safe_fetch("Telegram", fetch_iaea_telegram_signals)

        tasks = [
            loop.run_in_executor(None, run_adsb),
            loop.run_in_executor(None, run_notams),
            loop.run_in_executor(None, run_fp),
            loop.run_in_executor(None, run_press),
            loop.run_in_executor(None, run_telegram),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        def _unwrap(i: int, name: str) -> Dict[str, Any]:
            r = results[i]
            if isinstance(r, Exception):
                return {"correlation_hint": f"{name}: error.", "confidence": "low", "error": str(r)}
            return r if isinstance(r, dict) else {"correlation_hint": f"{name}: invalid response.", "confidence": "low"}

        adsb = _unwrap(0, "ADS-B")
        notam = _unwrap(1, "NOTAM")
        flight_plan = _unwrap(2, "Flight plan")
        press = _unwrap(3, "IAEA Press")
        telegram = _unwrap(4, "Telegram")

        result = correlate_iaea_tracker(
            adsb_result=adsb,
            notam_result=notam,
            flight_plan_result=flight_plan,
            press_result=press,
            telegram_result=telegram,
        )
        llm_summary = await _generate_haiku_summary_iaea(result)
        if llm_summary:
            result["summary"] = llm_summary
        return result

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        result = run_async(_run_all())
        duration_ms = int((time.perf_counter() - start) * 1000)
        oa = result.get("oeiii_adsb") or {}
        no = result.get("notams") or {}
        fp = result.get("flight_plan_status") or {}
        pr = result.get("iaea_press_grossi") or {}
        tg = result.get("iaea_telegram_signals") or {}
        source_results = [
            SourceResult(
                name="ADS-B",
                status="ok" if not oa.get("error") and (oa.get("count") or oa.get("aircraft")) else "error",
                fetched_at=fetched_at,
                record_count=oa.get("count", 0) or len(oa.get("aircraft") or []),
            ),
            SourceResult(
                name="NOTAMs",
                status="ok" if not no.get("error") and (no.get("count") or no.get("notams")) else "error",
                fetched_at=fetched_at,
                record_count=no.get("count", 0) or len(no.get("notams") or []),
            ),
            SourceResult(
                name="Flight plan",
                status="ok" if not fp.get("error") and fp.get("status") != "unknown" else "error",
                fetched_at=fetched_at,
            ),
            SourceResult(
                name="IAEA Press",
                status="ok" if not pr.get("error") and (pr.get("count") or pr.get("items")) else "error",
                fetched_at=fetched_at,
                record_count=pr.get("count", 0) or len(pr.get("items") or []),
            ),
            SourceResult(
                name="Telegram",
                status="ok" if not tg.get("error") and (tg.get("count") or tg.get("posts")) else "error",
                fetched_at=fetched_at,
                record_count=tg.get("count", 0) or len(tg.get("posts") or []),
            ),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "iaea_tracker", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = (
            "live" if ok_count >= 4 else "recent" if ok_count >= 2 else "stale" if ok_count >= 1 else "unavailable"
        )
        meta = AgentMetadata(
            agent="iaea_tracker",
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            sources=source_results,
            confidence=confidence,
            data_freshness=data_freshness,
            fallback_used=False,
            error_summary=None,
        )
        result["_meta"] = meta.model_dump(mode="json")
        return result
    except Exception as e:
        logger.exception("run_iaea_tracker failed")
        duration_ms = int((time.perf_counter() - start) * 1000)
        result = correlate_iaea_tracker(
            adsb_result={"correlation_hint": "Tracker failed.", "confidence": "low", "error": str(e)},
            notam_result={},
            flight_plan_result={},
            press_result={},
            telegram_result={},
        )
        meta = AgentMetadata(
            agent="iaea_tracker",
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            sources=[],
            confidence=compute_confidence_from_sources([]),
            data_freshness="unavailable",
            fallback_used=True,
            error_summary=str(e),
        )
        result["_meta"] = meta.model_dump(mode="json")
        return result
