"""
IAEA / OE-III Tracker – regelbasiertes Tracking von Rafael Grossi / IAEO-Flugzeug.

- ADS-B: gezieltes Mitlesen und Filtern nach OE-III (Austrian registration, IAEA DG aircraft).
- NOTAMs: Abruf von Luftraum-Informationen und Korrelation mit Flugdaten (Autorouter.aero / Eurocontrol EAD).
- IAEA-Pressemitteilungen: RSS/News von IAEA und Erwähnungen Rafael Grossi; Korrelation mit Flugdaten.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from .utils import run_async

# OE-III: österreichische Registration, typisch für das IAEA-DG-Flugzeug
OEIII_REGISTRATION = "OE-III"
OEIII_CALLSIGN_VARIANTS = ("OE-III", "OEIII", "OE III")

# ADS-B: Registration-Endpunkt (adsb.fi liefert nach Registration)
ADSB_REGISTRATION_ENDPOINTS = [
    "https://opendata.adsb.fi/api/v2/registration/{reg}",
    "https://api.adsb.lol/v2/registration/{reg}",
]
# Zusätzlich Region-Scan für Österreich / Europa / Naher Osten, dann Filter auf OE-III
ADSB_REGIONS_OEIII = [
    ("Vienna/Austria", 48.2, 16.4, 350),
    ("Eastern Med", 33.0, 35.0, 400),
    ("Persian Gulf", 26.0, 55.0, 450),
]
ADSB_LATLON_TEMPLATE = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{dist}"

# IAEA News/Press – RSS und Filter auf Grossi/Director General
IAEA_FEEDS = [
    "https://www.iaea.org/newscenter/news/feed",
    "https://www.iaea.org/newscenter/pressreleases/feed",
]
GROSSI_KEYWORDS = ("grossi", "director general", "dg grossi", "iaea chief", "rafael grossi")

# NOTAM – Autorouter.aero (Eurocontrol EAD) oder andere Quelle
# Beispiel: https://api.autorouter.aero/v1.0/notam (GET: itemas=["EDDS","LOWW"], offset=0, limit=100)
NOTAM_API_URL = os.getenv("NOTAM_API_URL", "https://api.autorouter.aero/v1.0/notam").strip()
NOTAM_API_KEY = os.getenv("NOTAM_API_KEY", "").strip()
# ICAO-Plätze für NOTAM-Abfrage (z. B. EDDS Stuttgart, LOWW Wien, OIIE Tehran)
NOTAM_ICAO_DEFAULT = ["EDDS", "LOWW", "OIIE"]


def _normalize_reg_callsign(s: Optional[str]) -> str:
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", "", s.strip().upper())


def _is_oeiii(ac: Dict[str, Any]) -> bool:
    """Prüft, ob ein Flugzeug-Obfekt OE-III (IAEA DG) ist."""
    reg = _normalize_reg_callsign(ac.get("r") or ac.get("registration") or "")
    flight = _normalize_reg_callsign(ac.get("flight") or ac.get("callsign") or "")
    if reg and "OEIII" in reg.replace("-", ""):
        return True
    if flight and any(v.replace("-", "") in flight for v in OEIII_CALLSIGN_VARIANTS):
        return True
    return False


async def _fetch_adsb_by_registration(client: httpx.AsyncClient, reg: str) -> List[Dict[str, Any]]:
    """Holt ADS-B-Daten für eine Registration (z. B. OE-III) von adsb.fi / adsb.lol."""
    reg_clean = reg.replace("-", "").strip()
    if not reg_clean:
        return []
    out = []
    for tpl in ADSB_REGISTRATION_ENDPOINTS:
        url = tpl.format(reg=reg_clean)
        try:
            resp = await client.get(url, timeout=12.0)
            if resp.status_code != 200:
                continue
            data = resp.json()
            ac = data if isinstance(data, list) else (data.get("ac") or data.get("aircraft") or [])
            if isinstance(ac, list) and ac:
                out.extend(ac)
                break
        except Exception:
            continue
    return out


async def _fetch_adsb_region(
    client: httpx.AsyncClient, lat: float, lon: float, dist: int
) -> List[Dict[str, Any]]:
    """Holt alle Flugzeuge in einer Region (lat/lon/dist NM) und filtert auf OE-III."""
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


def fetch_adsb_oeiii() -> Dict[str, Any]:
    """
    Liest ADS-B-Signale und filtert gezielt nach OE-III (IAEA DG Flugzeug).
    Nutzt Registration-Endpunkt und optional Region-Scans (Wien, Eastern Med, Persian Gulf).
    """
    async def _run() -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        seen_hex: set = set()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IAEA-Tracker/1.0)"}
        async with httpx.AsyncClient(headers=headers) as client:
            # 1) Direkt nach Registration OE-III
            by_reg = await _fetch_adsb_by_registration(client, OEIII_REGISTRATION)
            for ac in by_reg:
                icao = str(ac.get("hex") or "").strip().upper()
                if icao and icao not in seen_hex:
                    seen_hex.add(icao)
                    results.append(_normalize_aircraft(ac, "registration"))

            # 2) Region-Scans (nur wenn noch nichts gefunden oder um Abdeckung zu erhöhen)
            for label, lat, lon, dist in ADSB_REGIONS_OEIII:
                regional = await _fetch_adsb_region(client, lat, lon, dist)
                for ac in regional:
                    icao = str(ac.get("hex") or "").strip().upper()
                    if icao and icao not in seen_hex:
                        seen_hex.add(icao)
                        results.append(_normalize_aircraft(ac, label))
                await asyncio.sleep(0.3)  # Rate-Limit adsb.fi ~1/s

        return {
            "registration": OEIII_REGISTRATION,
            "aircraft": results,
            "count": len(results),
            "source": "adsb",
        }

    try:
        return run_async(_run())
    except Exception as e:
        return {"registration": OEIII_REGISTRATION, "aircraft": [], "count": 0, "error": str(e), "source": "adsb"}


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
    return {
        "hex": str(ac.get("hex") or "").strip().upper(),
        "flight": str(ac.get("flight") or ac.get("callsign") or "").strip(),
        "registration": str(ac.get("r") or ac.get("registration") or "").strip(),
        "type": str(ac.get("t") or ac.get("type") or "").strip(),
        "lat": lat_f,
        "lon": lon_f,
        "alt_baro": ac.get("alt_baro") or ac.get("altitude"),
        "region": region,
        "seen_at": ac.get("seen") or ac.get("timestamp"),
    }


def fetch_notams(
    days: int = 3,
    icao_locations: Optional[List[str]] = None,
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Holt NOTAMs für ICAO-Plätze (z. B. EDDS, LOWW, OIIE).

    Bei NOTAM_API_URL = https://api.autorouter.aero/v1.0/notam (Default):
    - GET mit itemas=["EDDS","LOWW",...] (JSON-Liste), offset, limit (max 100).
    - Antwort: { "total", "rows": [ { "id", "iteme" (Text), "startvalidity", "endvalidity", "itema" } ] }.
    """
    locations = (icao_locations or NOTAM_ICAO_DEFAULT)[:20]
    out: List[Dict[str, Any]] = []
    if not NOTAM_API_URL:
        return {"notams": [], "count": 0, "source": "notam"}

    is_autorouter = "autorouter.aero" in NOTAM_API_URL

    async def _get() -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params: Dict[str, Any] = {}
            if is_autorouter:
                # itemas: JSON-encoded list of ICAO identifiers
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
                if resp.status_code != 200:
                    return []
                data = resp.json()
                if is_autorouter and isinstance(data, dict):
                    return data.get("rows") or []
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("notams") or data.get("items") or data.get("rows") or []
            except Exception:
                pass
            return []

    try:
        out = run_async(_get())
    except Exception:
        out = []

    # Einheitliches Format für Korrelation (id, text, effective, expiry, location)
    notams: List[Dict[str, Any]] = []
    for n in (out or [])[:100]:
        if not isinstance(n, dict):
            notams.append({"id": "", "text": str(n), "effective": None, "expiry": None, "location": ""})
            continue
        if is_autorouter:
            # Autorouter: iteme = Text, startvalidity/endvalidity = Unix, itema = [ICAO, ...]
            itema = n.get("itema") or []
            location = ",".join(itema) if isinstance(itema, list) else str(itema)
            notams.append({
                "id": str(n.get("id") or n.get("nof") or ""),
                "text": (n.get("iteme") or n.get("itemd") or "").strip() or str(n.get("traffic") or ""),
                "effective": n.get("startvalidity"),
                "expiry": n.get("endvalidity"),
                "location": location,
            })
        else:
            notams.append({
                "id": str(n.get("id") or n.get("notam_id") or ""),
                "text": (n.get("text") or n.get("raw") or n.get("summary") or "").strip(),
                "effective": n.get("effective") or n.get("start") or n.get("startDate"),
                "expiry": n.get("expiry") or n.get("end") or n.get("endDate"),
                "location": n.get("location") or n.get("traffic") or "",
            })
    return {"notams": notams, "count": len(notams), "source": "notam"}


def fetch_iaea_press_releases(days: int = 14) -> Dict[str, Any]:
    """
    Holt IAEA-Pressemitteilungen und News (RSS) und filtert nach Rafael Grossi / Director General.
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
                items.append({
                    "title": title[:500],
                    "link": link,
                    "published": published,
                    "summary": (summary[:1000] if summary else ""),
                })
        except Exception:
            continue

    return {"items": items, "count": len(items), "source": "iaea_press"}


def correlate_iaea_tracker(
    adsb_result: Optional[Dict[str, Any]] = None,
    notam_result: Optional[Dict[str, Any]] = None,
    press_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Korreliert Flugdaten (OE-III), NOTAMs und IAEA-Pressemitteilungen (Rafael Grossi).
    Liefert ein kombiniertes Ergebnis mit Zeit-/Orts-Hinweisen für die Analyse.
    """
    adsb = adsb_result or fetch_adsb_oeiii()
    notam = notam_result or fetch_notams(days=3)
    press = press_result or fetch_iaea_press_releases(days=14)

    aircraft = (adsb.get("aircraft") or []) if isinstance(adsb, dict) else []
    notams = (notam.get("notams") or []) if isinstance(notam, dict) else []
    press_items = (press.get("items") or []) if isinstance(press, dict) else []

    # Einfache Korrelation: gleicher Zeitraum; bei vorhandener Position OE-III können NOTAMs
    # in der Region (später nach ICAO/Position erweiterbar) zugeordnet werden
    correlation_notes: List[str] = []
    if aircraft:
        correlation_notes.append(
            f"OE-III aktuell gemeldet: {len(aircraft)} Position(en) via ADS-B (adsb.fi/adsb.lol)."
        )
    else:
        correlation_notes.append("OE-III derzeit nicht in ADS-B-Daten sichtbar (am Boden oder außer Reichweite).")

    if notams:
        correlation_notes.append(f"{len(notams)} NOTAM(s) im Zeitraum – ggf. Luftraum-Einschränkungen für Reisen des DG.")
    if press_items:
        correlation_notes.append(
            f"{len(press_items)} IAEA-Pressemitteilungen/News mit Bezug zu Rafael Grossi im letzten Zeitraum."
        )

    return {
        "oeiii_adsb": {
            "registration": OEIII_REGISTRATION,
            "aircraft": aircraft,
            "count": len(aircraft),
        },
        "notams": {"notams": notams, "count": len(notams)},
        "iaea_press_grossi": {"items": press_items, "count": len(press_items)},
        "correlation_notes": correlation_notes,
        "summary": " | ".join(correlation_notes),
    }


def run_iaea_tracker() -> Dict[str, Any]:
    """
    Führt das komplette IAEA/OE-III-Tracking aus: ADS-B (OE-III), NOTAMs, IAEA-Press (Grossi)
    und Korrelation. Regelbasiert, keine LLM-Aufrufe.
    """
    adsb = fetch_adsb_oeiii()
    notam = fetch_notams(days=3)
    press = fetch_iaea_press_releases(days=14)
    return correlate_iaea_tracker(adsb_result=adsb, notam_result=notam, press_result=press)
