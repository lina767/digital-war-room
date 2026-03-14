"""
CHOKEPOINT Agent – Maritime chokepoint monitoring (Hormuz, Bab el-Mandeb, Suez).

Tracks tanker density, oil flow estimates, and disruption risk across key maritime
chokepoints. Uses a tiered data-quality model:
  - Tier 1 (live_ais): Spire Maritime / MarineTraffic / AISHub when API keys present
  - Tier 2 (estimated): EIA baseline + SIGINT warship proxy + news signals + oil spikes
  - Tier 3 (baseline_only): Static EIA baseline only

Disruption risk scoring uses explicit, tunable weights with EMA temporal smoothing.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import USER_AGENT, DEFAULT_TIMEOUT
from .utils import run_async, safe_float

logger = logging.getLogger(__name__)

# ── Chokepoint baselines (EIA / IEA published estimates, mbd) ────────────────

CHOKEPOINT_BASELINES = {
    "Strait of Hormuz": {
        "oil_flow_baseline_mbd": 20.5,
        "avg_daily_tankers": 30,
        "bbox": "55,25,58,27.5",
    },
    "Bab el-Mandeb": {
        "oil_flow_baseline_mbd": 6.2,
        "avg_daily_tankers": 12,
        "bbox": "43,12,44,13",
    },
    "Suez Canal": {
        "oil_flow_baseline_mbd": 5.5,
        "avg_daily_tankers": 15,
        "bbox": "32,29.8,33,31.3",
    },
}

# ── Disruption risk weights (explicit & tunable) ─────────────────────────────

DISRUPTION_WEIGHTS = {
    "tanker_density_anomaly": 0.25,
    "oil_price_volatility": 0.20,
    "military_presence": 0.20,
    "ais_anomalies": 0.15,
    "news_sentiment": 0.10,
    "diplomatic_signals": 0.10,
}

# Keywords for news-based chokepoint signal detection
CHOKEPOINT_NEWS_KEYWORDS = (
    "hormuz", "hormus", "bab el-mandeb", "bab al-mandab", "mandeb",
    "suez", "chokepoint", "strait", "blockade", "maritime",
    "tanker", "oil tanker", "shipping lane", "naval blockade",
    "houthi", "red sea attack", "sea lane",
)

TANKER_KEYWORDS = [
    "tanker", "crude", "vlcc", "suezmax", "aframax",
    "lpg", "lng", "oil", "chemical", "petroleum",
]

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "chokepoint_history.json"


# ── EMA temporal smoothing ───────────────────────────────────────────────────

def _ema_score(current: float, history: List[float], alpha: float = 0.3) -> float:
    """Exponential moving average: dampens single spikes, amplifies trends."""
    if not history:
        return current
    prev = history[-1]
    return alpha * current + (1 - alpha) * prev


def _load_history() -> Dict[str, List[float]]:
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text())
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_history(history: Dict[str, List[float]]) -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history, indent=2))
    except Exception as e:
        logger.debug("chokepoint: failed to save history: %s", e)


# ── Data fetching (tiered) ───────────────────────────────────────────────────

async def _fetch_aishub_tankers(bbox: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch tanker positions from AISHub (community, free). Returns None if unavailable."""
    api_key = (os.getenv("AISHUB_USERNAME") or "").strip()
    if not api_key:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        return None
    lon_min, lat_min, lon_max, lat_max = parts
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://data.aishub.net/ws.php",
                params={
                    "username": api_key,
                    "format": "1",
                    "output": "json",
                    "compress": "0",
                    "latmin": lat_min, "latmax": lat_max,
                    "lonmin": lon_min, "lonmax": lon_max,
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            records = data if isinstance(data, list) else data.get("data", data.get("records", []))
            if not isinstance(records, list):
                return None
            tankers = []
            for r in records:
                if not isinstance(r, dict):
                    continue
                ship_type = str(r.get("TYPE") or r.get("type") or r.get("ship_type") or "")
                name = str(r.get("NAME") or r.get("name") or "")
                is_tanker = (
                    ship_type.isdigit() and 80 <= int(ship_type) <= 89
                ) or any(kw in name.lower() for kw in TANKER_KEYWORDS)
                if is_tanker:
                    tankers.append({
                        "name": name,
                        "type": ship_type,
                        "lat": safe_float(r.get("LATITUDE") or r.get("latitude") or r.get("lat")),
                        "lon": safe_float(r.get("LONGITUDE") or r.get("longitude") or r.get("lon")),
                        "source": "aishub",
                    })
            return tankers
    except Exception as e:
        logger.debug("chokepoint: AISHub fetch failed: %s", e)
        return None


async def _fetch_spire_tankers(bbox: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch tankers from Spire Maritime AIS. Returns None if key not set."""
    token = (os.getenv("SPIRE_MARITIME_API_KEY") or os.getenv("SPIRE_API_KEY") or "").strip()
    if not token:
        return None
    base_url = os.getenv("SPIRE_MARITIME_BASE_URL", "https://api.sense.spire.com").rstrip("/")
    parts = bbox.split(",")
    if len(parts) != 4:
        return None
    lon_min, lat_min, lon_max, lat_max = [float(x) for x in parts]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base_url}/vessels",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params={"limit": 200},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            vessels = data if isinstance(data, list) else data.get("data", data.get("vessels", []))
            if not isinstance(vessels, list):
                return None
            tankers = []
            for v in vessels:
                lat = safe_float(v.get("latitude") or v.get("lat"))
                lon = safe_float(v.get("longitude") or v.get("lon"))
                if lat is None or lon is None:
                    continue
                if not (float(lat_min) <= lat <= float(lat_max) and float(lon_min) <= lon <= float(lon_max)):
                    continue
                name = v.get("name") or v.get("vessel_name") or ""
                ship_type = str(v.get("type") or v.get("ship_type") or v.get("vessel_type") or "")
                type_num = v.get("type_of_ship")
                is_tanker = (
                    (isinstance(type_num, int) and 80 <= type_num <= 89)
                    or any(kw in name.lower() for kw in TANKER_KEYWORDS)
                    or any(kw in ship_type.lower() for kw in TANKER_KEYWORDS)
                )
                if is_tanker:
                    tankers.append({
                        "name": name,
                        "type": ship_type or "tanker",
                        "lat": lat,
                        "lon": lon,
                        "source": "spire",
                    })
            return tankers
    except Exception as e:
        logger.debug("chokepoint: Spire tanker fetch failed: %s", e)
        return None


async def _fetch_marinetraffic_tankers(bbox: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch tankers from MarineTraffic API (paid). Returns None if key not set."""
    api_key = (os.getenv("MARINETRAFFIC_API_KEY") or "").strip()
    if not api_key:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        return None
    lon_min, lat_min, lon_max, lat_max = parts
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://services.marinetraffic.com/api/exportvessels/{api_key}",
                params={
                    "v": "8",
                    "MINLAT": lat_min, "MAXLAT": lat_max,
                    "MINLON": lon_min, "MAXLON": lon_max,
                    "SHIPTYPE": "7",
                    "msgtype": "simple",
                    "protocol": "jsono",
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list):
                return None
            return [
                {
                    "name": v.get("SHIPNAME") or "Tanker",
                    "type": v.get("SHIPTYPE") or "tanker",
                    "lat": safe_float(v.get("LAT")),
                    "lon": safe_float(v.get("LON")),
                    "source": "marinetraffic",
                }
                for v in data
                if isinstance(v, dict) and v.get("LAT")
            ]
    except Exception as e:
        logger.debug("chokepoint: MarineTraffic fetch failed: %s", e)
        return None


async def _fetch_eia_baseline() -> Dict[str, float]:
    """Fetch Persian Gulf oil export baseline from EIA API (monthly, free)."""
    api_key = (os.getenv("EIA_API_KEY") or "").strip()
    if not api_key:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.eia.gov/v2/international/data/",
                params={
                    "api_key": api_key,
                    "frequency": "monthly",
                    "data[0]": "value",
                    "facets[productId][]": "57",
                    "facets[countryRegionId][]": "WORLD",
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": "1",
                },
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            records = (data.get("response") or {}).get("data") or []
            if records and isinstance(records[0], dict):
                val = safe_float(records[0].get("value"))
                if val:
                    return {"world_oil_production_mbd": val / 1000.0}
    except Exception as e:
        logger.debug("chokepoint: EIA fetch failed: %s", e)
    return {}


# ── Scoring ──────────────────────────────────────────────────────────────────

def _compute_sub_scores(
    tanker_count: int,
    baseline_tankers: int,
    oil_change_pct: float,
    military_count: int,
    ais_anomaly_count: int,
    news_hit_count: int,
    diplo_signal_count: int,
) -> Dict[str, float]:
    """Compute normalized 0-100 sub-scores for each disruption dimension."""
    # Tanker density anomaly: deviation from baseline (both directions matter)
    if baseline_tankers > 0 and tanker_count > 0:
        ratio = tanker_count / baseline_tankers
        tanker_sub = min(100.0, abs(1.0 - ratio) * 200)
    else:
        tanker_sub = 50.0  # unknown = moderate

    # Oil price volatility
    oil_sub = min(100.0, abs(oil_change_pct) * 10)

    # Military presence
    mil_sub = min(100.0, military_count * 8.0)

    # AIS anomalies (dark ships / spoofing)
    ais_sub = min(100.0, ais_anomaly_count * 20.0)

    # News sentiment
    news_sub = min(100.0, news_hit_count * 15.0)

    # Diplomatic signals
    diplo_sub = min(100.0, diplo_signal_count * 20.0)

    return {
        "tanker_density_anomaly": tanker_sub,
        "oil_price_volatility": oil_sub,
        "military_presence": mil_sub,
        "ais_anomalies": ais_sub,
        "news_sentiment": news_sub,
        "diplomatic_signals": diplo_sub,
    }


def _weighted_score(sub_scores: Dict[str, float]) -> float:
    total = sum(
        sub_scores.get(k, 0) * w
        for k, w in DISRUPTION_WEIGHTS.items()
    )
    return min(100.0, max(0.0, total))


def _density_label(tanker_count: int, baseline: int) -> str:
    if baseline <= 0 or tanker_count <= 0:
        return "unknown"
    ratio = tanker_count / baseline
    if ratio < 0.5:
        return "low"
    if ratio < 1.3:
        return "normal"
    if ratio < 2.0:
        return "elevated"
    return "congested"


def _status_from_risk(risk: float) -> str:
    if risk >= 70:
        return "DISRUPTED"
    if risk >= 40:
        return "RESTRICTED"
    return "OPEN"


# ── Main agent function ─────────────────────────────────────────────────────

def run_chokepoint_agent(conflict: str) -> Dict[str, Any]:
    """Run CHOKEPOINT agent: monitors Hormuz, Bab el-Mandeb, Suez."""

    async def _run() -> Dict[str, Any]:
        history = _load_history()
        eia_data = await _fetch_eia_baseline()
        chokepoints = []

        for cp_name, baseline in CHOKEPOINT_BASELINES.items():
            bbox = baseline["bbox"]
            avg_tankers = baseline["avg_daily_tankers"]
            oil_baseline = baseline["oil_flow_baseline_mbd"]

            # Try tiered tanker data
            tankers: Optional[List[Dict]] = None
            data_quality = "baseline_only"

            tankers = await _fetch_spire_tankers(bbox)
            if tankers is not None:
                data_quality = "live_ais"
            else:
                tankers = await _fetch_marinetraffic_tankers(bbox)
                if tankers is not None:
                    data_quality = "live_ais"
                else:
                    tankers = await _fetch_aishub_tankers(bbox)
                    if tankers is not None:
                        data_quality = "live_ais"

            tanker_count = len(tankers) if tankers is not None else 0

            if data_quality != "live_ais":
                # Tier 2/3: estimate from baseline
                tanker_count = avg_tankers
                data_quality = "estimated" if eia_data else "baseline_only"

            # Oil flow estimate: scale baseline by tanker ratio
            if avg_tankers > 0 and tanker_count > 0:
                flow_ratio = tanker_count / avg_tankers
                oil_flow = oil_baseline * min(2.0, max(0.1, flow_ratio))
            else:
                oil_flow = oil_baseline

            # Placeholder counts (filled from supervisor context post-collection)
            cp_entry = {
                "name": cp_name,
                "tanker_count": tanker_count,
                "tanker_density": _density_label(tanker_count, avg_tankers),
                "oil_flow_estimate_mbd": round(oil_flow, 1),
                "military_vessels": 0,
                "ais_anomalies": 0,
                "brent_impact_pct": 0.0,
                "disruption_risk": 0.0,
                "status": "OPEN",
                "data_quality": data_quality,
                "tanker_details": (tankers or [])[:20],
            }
            chokepoints.append(cp_entry)

        # Compute scores (enriched later by supervisor with cross-agent data)
        total_risk = 0.0
        for cp in chokepoints:
            sub = _compute_sub_scores(
                tanker_count=cp["tanker_count"],
                baseline_tankers=CHOKEPOINT_BASELINES[cp["name"]]["avg_daily_tankers"],
                oil_change_pct=cp["brent_impact_pct"],
                military_count=cp["military_vessels"],
                ais_anomaly_count=cp["ais_anomalies"],
                news_hit_count=0,
                diplo_signal_count=0,
            )
            raw_risk = _weighted_score(sub)
            cp_history = history.get(cp["name"], [])
            smoothed = _ema_score(raw_risk, cp_history)
            cp["disruption_risk"] = round(smoothed, 1)
            cp["status"] = _status_from_risk(smoothed)

            cp_history.append(round(smoothed, 1))
            history[cp["name"]] = cp_history[-30:]
            total_risk += smoothed

        _save_history(history)

        chokepoint_score = round(total_risk / max(len(chokepoints), 1), 1)

        parts = []
        for cp in chokepoints:
            parts.append(
                f"{cp['name']}: {cp['status']} "
                f"(risk {cp['disruption_risk']:.0f}, "
                f"~{cp['oil_flow_estimate_mbd']} mbd, "
                f"{cp['tanker_count']} tankers [{cp['data_quality']}])"
            )
        summary = "CHOKEPOINT: " + "; ".join(parts)

        return {
            "chokepoints": chokepoints,
            "chokepoint_score": chokepoint_score,
            "summary": summary,
        }

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception("CHOKEPOINT agent error: %s", e)
        return {
            "chokepoints": [],
            "chokepoint_score": 0.0,
            "summary": f"CHOKEPOINT error: {e}",
        }


def enrich_chokepoints(
    chokepoint_data: Dict[str, Any],
    sigint_data: Dict[str, Any],
    energy_data: Dict[str, Any],
    news_data: Dict[str, Any],
    diplo_data: Dict[str, Any],
    compliance_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Post-collection enrichment: cross-reference with other agent data.

    Called by the supervisor after all agents have run to inject military vessel
    counts, oil price impacts, AIS anomalies, and news/diplo signals into each
    chokepoint entry, then recompute disruption_risk with full data.
    """
    from compliance.zones import CHOKEPOINT_ZONES

    history = _load_history()
    chokepoints = chokepoint_data.get("chokepoints") or []
    if not chokepoints:
        return chokepoint_data

    # Count military vessels per chokepoint zone
    ships = sigint_data.get("ships") or []
    mil_by_cp: Dict[str, int] = {cp: 0 for cp in CHOKEPOINT_BASELINES}
    for s in ships:
        if not isinstance(s, dict):
            continue
        lat = safe_float(s.get("lat"))
        lon = safe_float(s.get("lon"))
        if lat is None or lon is None:
            continue
        for cp_name, zone in CHOKEPOINT_ZONES.items():
            if zone.contains(lat, lon):
                mil_by_cp[cp_name] = mil_by_cp.get(cp_name, 0) + 1

    # Oil price impact
    brent_pct = 0.0
    for c in (energy_data.get("commodities") or []):
        if isinstance(c, dict) and c.get("symbol") == "BRENT":
            brent_pct = safe_float(c.get("change_pct_raw")) or 0.0
            break

    # News hits
    news_hits = 0
    for art in (news_data.get("articles") or []):
        if isinstance(art, dict) and art.get("title"):
            title_lower = art["title"].lower()
            if any(kw in title_lower for kw in CHOKEPOINT_NEWS_KEYWORDS):
                news_hits += 1

    # Diplo signals
    diplo_signals = 0
    if diplo_data.get("ofac_sdn", {}).get("total_matches"):
        diplo_signals += 1
    if diplo_data.get("un_icj_news"):
        diplo_signals += len([n for n in diplo_data["un_icj_news"]
                              if isinstance(n, dict) and "error" not in n])

    # AIS anomalies from compliance
    ais_total = 0
    if compliance_data:
        ais_total = len(compliance_data.get("ais_anomalies") or [])

    for cp in chokepoints:
        cp_name = cp["name"]
        cp["military_vessels"] = mil_by_cp.get(cp_name, 0)
        cp["brent_impact_pct"] = round(brent_pct, 2)
        cp["ais_anomalies"] = ais_total

        sub = _compute_sub_scores(
            tanker_count=cp["tanker_count"],
            baseline_tankers=CHOKEPOINT_BASELINES.get(cp_name, {}).get("avg_daily_tankers", 30),
            oil_change_pct=brent_pct,
            military_count=cp["military_vessels"],
            ais_anomaly_count=cp["ais_anomalies"],
            news_hit_count=news_hits,
            diplo_signal_count=diplo_signals,
        )
        raw_risk = _weighted_score(sub)
        cp_history = history.get(cp_name, [])
        smoothed = _ema_score(raw_risk, cp_history)
        cp["disruption_risk"] = round(smoothed, 1)
        cp["status"] = _status_from_risk(smoothed)

        cp_history.append(round(smoothed, 1))
        history[cp_name] = cp_history[-30:]

    _save_history(history)

    total_risk = sum(cp["disruption_risk"] for cp in chokepoints)
    chokepoint_data["chokepoint_score"] = round(total_risk / max(len(chokepoints), 1), 1)

    parts = []
    for cp in chokepoints:
        parts.append(
            f"{cp['name']}: {cp['status']} "
            f"(risk {cp['disruption_risk']:.0f}, "
            f"~{cp['oil_flow_estimate_mbd']} mbd, "
            f"{cp['tanker_count']} tankers [{cp['data_quality']}])"
        )
    chokepoint_data["summary"] = "CHOKEPOINT: " + "; ".join(parts)

    return chokepoint_data
