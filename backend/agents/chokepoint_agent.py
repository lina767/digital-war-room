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

# EIA / IEA H1 2025 figures (World Oil Transit Chokepoints, updated Mar 2026)
CHOKEPOINT_BASELINES = {
    "Strait of Hormuz": {
        "oil_flow_baseline_mbd": 20.9,
        "avg_daily_tankers": 30,
        "bbox": "55,25,58,27.5",
    },
    "Bab el-Mandeb": {
        "oil_flow_baseline_mbd": 4.2,
        "avg_daily_tankers": 8,
        "bbox": "43,12,44,13",
    },
    "Suez Canal": {
        "oil_flow_baseline_mbd": 4.9,
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
DISRUPTION_WEIGHTS_NO_AIS = {
    "tanker_density_anomaly": 0.10,
    "oil_price_volatility": 0.25,
    "military_presence": 0.15,
    "ais_anomalies": 0.05,
    "news_sentiment": 0.30,
    "diplomatic_signals": 0.15,
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
BRENT_HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "brent_history.json"
OVERRIDES_FILE = Path(__file__).resolve().parent.parent / "data" / "chokepoint_overrides.json"

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERIES = {
    "Strait of Hormuz": '"strait of hormuz" (blockade OR closed OR disrupted OR "no transit" OR IRGC)',
    "Bab el-Mandeb": '("bab el-mandeb" OR "bab al-mandab") (houthi OR blockade OR suspended OR reroute)',
    "Suez Canal": '"suez canal" (suspended OR halted OR reroute OR "cape of good hope")',
}
# Narrow closure-only queries: if hits_closure_24h > 0, force DISRUPTED (hard override)
GDELT_QUERIES_CLOSURE = {
    "Strait of Hormuz": '"strait of hormuz" (closed OR shut OR "no transit" OR blockaded)',
    "Bab el-Mandeb": '("bab el-mandeb" OR "bab al-mandab") (closed OR shut OR blockaded OR "no transit")',
    "Suez Canal": '"suez canal" (closed OR shut OR blockaded OR "no transit")',
}
CHOKEPOINT_SATURATION = {
    "Strait of Hormuz": 15,  # lowered so closure-level GDELT hits yield strong signal
    "Bab el-Mandeb": 12,
    "Suez Canal": 20,
}
# Minimum risk when data_quality is baseline_only; unknown != safe
BASELINE_ONLY_RISK_FLOOR = 15.0
# When GDELT disruption hits exceed these, enforce minimum risk so status reflects closure
GDELT_RISK_FLOOR_HIGH = 75.0   # gdelt_24h >= 10 -> at least DISRUPTED
GDELT_RISK_FLOOR_MED = 50.0    # gdelt_24h >= 5  -> at least CONTESTED
GDELT_RISK_FLOOR_LOW = 30.0    # gdelt_24h >= 3  -> at least RESTRICTED
GDELT_THRESHOLD_HIGH = 10
GDELT_THRESHOLD_MED = 5
GDELT_THRESHOLD_LOW = 3
# Live-AIS: if tanker_count < avg * this ratio, enforce DISRUPTED-level risk
LIVE_AIS_DISRUPTED_RATIO = 0.3
# Live-AIS: if tanker_count < avg * this ratio (and >= above), enforce CONTESTED-level risk
LIVE_AIS_RESTRICTED_RATIO = 0.5
# Optional external status URL returning JSON {"Strait of Hormuz": "DISRUPTED", ...}
CHOKEPOINT_STATUS_URL_ENV = "CHOKEPOINT_STATUS_URL"
# Brent signal threshold (percent move); env CHOKEPOINT_BRENT_PCT_THRESHOLD overrides
BRENT_PCT_THRESHOLD_DEFAULT = 5.0
# GDELT 6h window: if hits_6h >= this, apply at least CONTESTED risk floor
GDELT_6H_THRESHOLD = 2
GDELT_RISK_FLOOR_6H = 50.0

# ── EMA temporal smoothing ───────────────────────────────────────────────────

def _ema_score(current: float, history: List[float], alpha: float = 0.3) -> float:
    """Exponential moving average: dampens single spikes, amplifies trends. Crisis-aware: high alpha on spike."""
    if not history:
        return current
    prev = history[-1]
    effective_alpha = 0.7 if current > prev + 20 else alpha
    return effective_alpha * current + (1 - effective_alpha) * prev


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


def _load_brent_history() -> List[float]:
    try:
        if BRENT_HISTORY_FILE.exists():
            data = json.loads(BRENT_HISTORY_FILE.read_text())
            if isinstance(data, list):
                return [float(x) for x in data if isinstance(x, (int, float))]
    except Exception:
        pass
    return []


def _save_brent_history(prices: List[float]) -> None:
    try:
        BRENT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        BRENT_HISTORY_FILE.write_text(json.dumps(prices[-30:], indent=0))
    except Exception as e:
        logger.debug("chokepoint: failed to save brent history: %s", e)


def _load_overrides() -> Dict[str, str]:
    """Load manual status overrides from JSON (e.g. from UI). Keys: chokepoint name, values: OPEN|RESTRICTED|CONTESTED|DISRUPTED."""
    try:
        if OVERRIDES_FILE.exists():
            data = json.loads(OVERRIDES_FILE.read_text())
            if isinstance(data, dict):
                return {k: str(v).upper() for k, v in data.items() if str(v).upper() in ("OPEN", "RESTRICTED", "CONTESTED", "DISRUPTED")}
    except Exception:
        pass
    return {}


def _save_overrides(overrides: Dict[str, str]) -> None:
    try:
        OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES_FILE.write_text(json.dumps(overrides, indent=2))
    except Exception as e:
        logger.debug("chokepoint: failed to save overrides: %s", e)


async def _fetch_external_status() -> Dict[str, str]:
    """Fetch optional external status JSON from CHOKEPOINT_STATUS_URL. Returns dict cp_name -> OPEN|RESTRICTED|CONTESTED|DISRUPTED."""
    url = (os.getenv(CHOKEPOINT_STATUS_URL_ENV) or "").strip()
    if not url:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            if not isinstance(data, dict):
                return {}
            return {k: str(v).upper() for k, v in data.items() if str(v).upper() in ("OPEN", "RESTRICTED", "CONTESTED", "DISRUPTED")}
    except Exception as e:
        logger.debug("chokepoint: external status fetch failed: %s", e)
        return {}


def _risk_for_status(status: str) -> float:
    if status == "DISRUPTED":
        return 75.0
    if status == "CONTESTED":
        return 50.0
    if status == "RESTRICTED":
        return 30.0
    return 0.0


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


async def _fetch_gdelt_one(query: str, timespan: str) -> int:
    """Fetch GDELT artlist for one query and timespan; return article count."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                GDELT_URL,
                params={
                    "query": query,
                    "mode": "artlist",
                    "format": "json",
                    "timespan": timespan,
                    "maxrecords": 50,
                },
            )
            if resp.status_code != 200:
                return 0
            data = resp.json()
            if isinstance(data, list):
                return len(data)
            for key in ("articles", "articleList", "results", "docs", "ArticleList"):
                out = (data.get(key) if isinstance(data, dict) else None)
                if isinstance(out, list):
                    return len(out)
            return 0
    except Exception as e:
        logger.debug("chokepoint: GDELT fetch failed: %s", e)
        return 0


async def _fetch_gdelt_chokepoint_events() -> Dict[str, Dict[str, int]]:
    """GDELT per chokepoint: 24h, 72h, 6h, and narrow closure query (hits_closure_24h)."""
    tasks = []
    keys = []
    for cp_name, query in GDELT_QUERIES.items():
        tasks.append(_fetch_gdelt_one(query, "24H"))
        keys.append((cp_name, "hits_24h"))
        tasks.append(_fetch_gdelt_one(query, "72H"))
        keys.append((cp_name, "hits_72h"))
        tasks.append(_fetch_gdelt_one(query, "6H"))
        keys.append((cp_name, "hits_6h"))
    for cp_name, query in GDELT_QUERIES_CLOSURE.items():
        tasks.append(_fetch_gdelt_one(query, "24H"))
        keys.append((cp_name, "hits_closure_24h"))
    results = await asyncio.gather(*tasks)
    out: Dict[str, Dict[str, int]] = {
        "Strait of Hormuz": {"hits_24h": 0, "hits_72h": 0, "hits_6h": 0, "hits_closure_24h": 0},
        "Bab el-Mandeb": {"hits_24h": 0, "hits_72h": 0, "hits_6h": 0, "hits_closure_24h": 0},
        "Suez Canal": {"hits_24h": 0, "hits_72h": 0, "hits_6h": 0, "hits_closure_24h": 0},
    }
    for (cp_name, key), count in zip(keys, results):
        out[cp_name][key] = count
    return out


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

    # Oil price volatility (cap at 100 for >=10% move)
    oil_sub = 100.0 if abs(oil_change_pct) >= 10 else min(100.0, abs(oil_change_pct) * 15)

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


def _weighted_score(sub_scores: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
    w = weights or DISRUPTION_WEIGHTS
    total = sum(sub_scores.get(k, 0) * w.get(k, 0) for k in w)
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
    if risk >= 75:
        return "DISRUPTED"
    if risk >= 50:
        return "CONTESTED"
    if risk >= 30:
        return "RESTRICTED"
    return "OPEN"


def _disruption_factor(cp_name: str, gdelt_24h: int, gdelt_72h: int) -> float:
    """Continuous disruption factor 0..1 from GDELT hits; per-chokepoint saturation; decay when 24h << 72h."""
    threshold = CHOKEPOINT_SATURATION.get(cp_name, 15)
    acute = min(1.0, gdelt_24h / threshold)
    if gdelt_72h > 0 and gdelt_24h < gdelt_72h * 0.3:
        acute *= 0.5
    return acute


def _gdelt_risk_floor(gdelt_24h: int, hits_closure_24h: int = 0, hits_6h: int = 0) -> float:
    """Minimum risk when GDELT shows significant disruption/closure coverage."""
    floor = 0.0
    if hits_closure_24h > 0:
        floor = max(floor, GDELT_RISK_FLOOR_HIGH)  # hard override: explicit closure wording
    if gdelt_24h >= GDELT_THRESHOLD_HIGH:
        floor = max(floor, GDELT_RISK_FLOOR_HIGH)
    elif gdelt_24h >= GDELT_THRESHOLD_MED:
        floor = max(floor, GDELT_RISK_FLOOR_MED)
    elif gdelt_24h >= GDELT_THRESHOLD_LOW:
        floor = max(floor, GDELT_RISK_FLOOR_LOW)
    if hits_6h >= GDELT_6H_THRESHOLD:
        floor = max(floor, GDELT_RISK_FLOOR_6H)
    return floor


# ── Main agent function ─────────────────────────────────────────────────────

def run_chokepoint_agent(conflict: str) -> Dict[str, Any]:
    """Run CHOKEPOINT agent: monitors Hormuz, Bab el-Mandeb, Suez."""

    async def _run() -> Dict[str, Any]:
        history = _load_history()
        eia_data_task = _fetch_eia_baseline()
        gdelt_task = _fetch_gdelt_chokepoint_events()
        eia_data = await eia_data_task
        gdelt_disruption = await gdelt_task
        external_status = await _fetch_external_status()
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
            gdelt = gdelt_disruption.get(cp["name"], {})
            gdelt_24h = gdelt.get("hits_24h", 0)
            hits_closure_24h = gdelt.get("hits_closure_24h", 0)
            hits_6h = gdelt.get("hits_6h", 0)
            news_hit_count = min(10, gdelt_24h)
            sub = _compute_sub_scores(
                tanker_count=cp["tanker_count"],
                baseline_tankers=CHOKEPOINT_BASELINES[cp["name"]]["avg_daily_tankers"],
                oil_change_pct=cp["brent_impact_pct"],
                military_count=cp["military_vessels"],
                ais_anomaly_count=cp["ais_anomalies"],
                news_hit_count=news_hit_count,
                diplo_signal_count=0,
            )
            raw_risk = _weighted_score(sub)
            cp_history = history.get(cp["name"], [])
            smoothed = _ema_score(raw_risk, cp_history)
            if cp["data_quality"] == "baseline_only":
                smoothed = max(smoothed, BASELINE_ONLY_RISK_FLOOR)
            avg_t = CHOKEPOINT_BASELINES[cp["name"]]["avg_daily_tankers"]
            if cp["data_quality"] == "live_ais" and avg_t > 0 and cp["tanker_count"] < avg_t * LIVE_AIS_DISRUPTED_RATIO:
                smoothed = max(smoothed, GDELT_RISK_FLOOR_HIGH)
            elif cp["data_quality"] == "live_ais" and avg_t > 0 and cp["tanker_count"] < avg_t * LIVE_AIS_RESTRICTED_RATIO:
                smoothed = max(smoothed, GDELT_RISK_FLOOR_MED)
            gdelt_floor = _gdelt_risk_floor(gdelt_24h, hits_closure_24h=hits_closure_24h, hits_6h=hits_6h)
            if gdelt_floor > 0:
                smoothed = max(smoothed, gdelt_floor)
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
            "gdelt_disruption": gdelt_disruption,
            "external_status": external_status,
        }

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception("CHOKEPOINT agent error: %s", e)
        return {
            "chokepoints": [],
            "chokepoint_score": 0.0,
            "summary": f"CHOKEPOINT error: {e}",
            "gdelt_disruption": {},
            "external_status": {},
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

    # Oil price impact and brent baseline for confirmation gate
    brent_pct = 0.0
    brent_price_current: Optional[float] = None
    for c in (energy_data.get("commodities") or []):
        if isinstance(c, dict) and c.get("symbol") == "BRENT":
            brent_pct = safe_float(c.get("change_pct_raw")) or 0.0
            brent_price_current = safe_float(c.get("price"))
            break

    brent_above_baseline_pct: Optional[float] = None
    brent_history = _load_brent_history()
    if brent_price_current is not None:
        brent_history.append(brent_price_current)
        _save_brent_history(brent_history)
        if len(brent_history) >= 7:
            mean_baseline = sum(brent_history[:-1]) / (len(brent_history) - 1)
            if mean_baseline and mean_baseline > 0:
                brent_above_baseline_pct = ((brent_price_current - mean_baseline) / mean_baseline) * 100.0

    # Per-chokepoint news disruption count (pre-tagged by NEWS agent)
    news_disruption_by_cp: Dict[str, int] = {cp["name"]: 0 for cp in chokepoints}
    for art in (news_data.get("articles") or []):
        if not isinstance(art, dict) or not art.get("is_disruption"):
            continue
        for tag in art.get("chokepoint_tags") or []:
            if tag in news_disruption_by_cp:
                news_disruption_by_cp[tag] += 1

    gdelt_disruption = chokepoint_data.get("gdelt_disruption") or {}

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

    try:
        brent_threshold = float(os.getenv("CHOKEPOINT_BRENT_PCT_THRESHOLD", str(BRENT_PCT_THRESHOLD_DEFAULT)))
    except (TypeError, ValueError):
        brent_threshold = BRENT_PCT_THRESHOLD_DEFAULT
    brent_signal = abs(brent_pct) >= float(brent_threshold) or (brent_above_baseline_pct is not None and brent_above_baseline_pct >= 8.0)

    # Merge external status (from URL) and manual overrides (from UI); overrides take precedence
    external_status = chokepoint_data.get("external_status") or {}
    status_overrides = dict(external_status, **_load_overrides())

    for cp in chokepoints:
        cp_name = cp["name"]
        cp["military_vessels"] = mil_by_cp.get(cp_name, 0)
        cp["brent_impact_pct"] = round(brent_pct, 2)
        cp["ais_anomalies"] = ais_total

        gdelt = gdelt_disruption.get(cp_name, {})
        gdelt_24h = gdelt.get("hits_24h", 0)
        gdelt_72h = gdelt.get("hits_72h", 0)
        hits_closure_24h = gdelt.get("hits_closure_24h", 0)
        hits_6h = gdelt.get("hits_6h", 0)
        news_disruption_count = news_disruption_by_cp.get(cp_name, 0)

        # Confirmation gate: 2 of 3 for live_ais; 1 of 3 for estimated/baseline_only
        sig_gdelt = gdelt_24h >= 3
        sig_news = news_disruption_count >= 1
        sig_brent = brent_signal
        required_signals = 1 if cp.get("data_quality") != "live_ais" else 2
        confirmed = sum([sig_gdelt, sig_news, sig_brent]) >= required_signals
        unconfirmed_one = (
            sum([sig_gdelt, sig_news, sig_brent]) == 1
            if cp.get("data_quality") == "live_ais"
            else False
        )

        baseline_info = CHOKEPOINT_BASELINES.get(cp_name, {})
        avg_tankers = baseline_info.get("avg_daily_tankers", 30)
        oil_baseline = baseline_info.get("oil_flow_baseline_mbd", 5.0)

        if cp.get("data_quality") != "live_ais":
            if confirmed:
                factor = _disruption_factor(cp_name, gdelt_24h, gdelt_72h)
                tanker_count = max(1, int(avg_tankers * (1.0 - factor * 0.95)))
                cp["tanker_count"] = tanker_count
                if avg_tankers > 0 and oil_baseline > 0:
                    cp["oil_flow_estimate_mbd"] = round(oil_baseline * (tanker_count / avg_tankers), 1)
                cp["tanker_density"] = _density_label(tanker_count, avg_tankers)
            elif unconfirmed_one:
                factor = 0.3
                tanker_count = max(1, int(avg_tankers * (1.0 - factor * 0.95)))
                cp["tanker_count"] = tanker_count
                if avg_tankers > 0 and oil_baseline > 0:
                    cp["oil_flow_estimate_mbd"] = round(oil_baseline * (tanker_count / avg_tankers), 1)
                cp["tanker_density"] = _density_label(tanker_count, avg_tankers)

        use_weights = DISRUPTION_WEIGHTS_NO_AIS if cp.get("data_quality") != "live_ais" else DISRUPTION_WEIGHTS
        news_hits_cp = news_disruption_by_cp.get(cp_name, 0) or min(10, gdelt_24h)

        sub = _compute_sub_scores(
            tanker_count=cp["tanker_count"],
            baseline_tankers=avg_tankers,
            oil_change_pct=brent_pct,
            military_count=cp["military_vessels"],
            ais_anomaly_count=cp["ais_anomalies"],
            news_hit_count=news_hits_cp,
            diplo_signal_count=diplo_signals,
        )
        raw_risk = _weighted_score(sub, use_weights)
        cp_history = history.get(cp_name, [])
        smoothed = _ema_score(raw_risk, cp_history)
        if cp.get("data_quality") == "baseline_only":
            smoothed = max(smoothed, BASELINE_ONLY_RISK_FLOOR)
        if cp.get("data_quality") == "live_ais" and avg_tankers > 0 and cp["tanker_count"] < avg_tankers * LIVE_AIS_DISRUPTED_RATIO:
            smoothed = max(smoothed, GDELT_RISK_FLOOR_HIGH)
        elif cp.get("data_quality") == "live_ais" and avg_tankers > 0 and cp["tanker_count"] < avg_tankers * LIVE_AIS_RESTRICTED_RATIO:
            smoothed = max(smoothed, GDELT_RISK_FLOOR_MED)
        gdelt_floor = _gdelt_risk_floor(gdelt_24h, hits_closure_24h=hits_closure_24h, hits_6h=hits_6h)
        if gdelt_floor > 0:
            smoothed = max(smoothed, gdelt_floor)
        cp["disruption_risk"] = round(smoothed, 1)
        cp["status"] = _status_from_risk(smoothed)
        if cp_name in status_overrides:
            cp["status"] = status_overrides[cp_name]
            cp["disruption_risk"] = round(_risk_for_status(cp["status"]), 1)

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
