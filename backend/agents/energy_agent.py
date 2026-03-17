"""
ENERGY / Commodities Agent – commodity indices, food & fertilizer.
Fetches: oil (EIA then FRED then Alpha Vantage), food (FRED then Alpha Vantage),
FAO Food Price Index, World Bank fertilizer prices, and computes food_security_risk.
Rule-based score from price volatility. No LLM. (AGSI+ removed – was unreliable.)
"""
import asyncio
import csv
import io
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from .health_registry import get_health_registry
from .utils import (
    AgentMetadata,
    SourceResult,
    run_async,
    utc_now_iso,
    compute_confidence_from_sources,
)

logger = logging.getLogger(__name__)

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
EIA_BASE = "https://api.eia.gov/v2/seriesid"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
# EIA spot price series (daily)
EIA_BRENT_SERIES = "PET.RBRTE.D"
EIA_WTI_SERIES = "PET.RWTC.D"
# FRED: oil daily, food monthly
FRED_OIL_SERIES = [("DCOILBRENTEU", "BRENT", "Brent crude"), ("DCOILWTICO", "WTI", "WTI crude")]
FRED_FOOD_SERIES = [("PWHEAMTUSDM", "WHEAT", "Wheat"), ("PMAIZMTUSDM", "CORN", "Corn"), ("PSOYBUSDM", "SOYBEAN", "Soybean")]

OIL_SYMBOLS = [
    ("BRENT", "Brent crude"),
    ("WTI", "WTI crude"),
]

FOOD_SYMBOLS = [
    ("WHEAT", "Wheat"),
    ("CORN", "Corn"),
    ("SOYBEAN", "Soybean"),
]

COMMODITY_SYMBOLS = OIL_SYMBOLS + FOOD_SYMBOLS

# FAO Food Price Index CSV (free, monthly). FAO may change the filename (e.g. _mar, _apr); override via FAO_FPI_URL env if 404.
FAO_FPI_URL = os.getenv(
    "FAO_FPI_URL",
    "https://www.fao.org/media/docs/worldfoodsituationlibraries/default-document-library/food_price_indices_data_csv_mar.csv",
)

# World Bank commodity prices API (free, monthly)
WORLD_BANK_COMMODITIES_URL = "https://api.worldbank.org/v2/country/WLD/indicator"
UREA_INDICATOR = "COMMODITY.FERTILIZER.UREA"
DAP_INDICATOR = "COMMODITY.FERTILIZER.DAP"

# Countries heavily exposed to food imports via Hormuz / Bab el-Mandeb
EXPOSED_COUNTRIES = ["Egypt", "Yemen", "Somalia", "Djibouti", "Ethiopia", "Sudan"]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _fetch_fao_fpi() -> Dict[str, Any]:
    """Fetch FAO Food Price Index (monthly, free CSV)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FAO_FPI_URL, follow_redirects=True)
            if resp.status_code != 200:
                if resp.status_code == 404:
                    logger.warning(
                        "ENERGY: FAO FPI URL returned 404 (file may have been moved). Set FAO_FPI_URL env to current CSV URL."
                    )
                return {"error": f"FAO FPI HTTP {resp.status_code}"}
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)
            if len(rows) < 3:
                return {"error": "FAO FPI: insufficient data"}
            header = [h.strip().lower() for h in rows[0]]
            # Find "food price index" or "date" columns
            date_col = next((i for i, h in enumerate(header) if "date" in h), 0)
            fpi_col = next(
                (i for i, h in enumerate(header) if "food" in h and "price" in h and "index" in h),
                next((i for i, h in enumerate(header) if "nominal" in h), 1),
            )
            latest = rows[-1]
            prev_year_row = rows[-13] if len(rows) > 13 else rows[1]
            index_val = _safe_float(latest[fpi_col]) if fpi_col < len(latest) else None
            prev_val = _safe_float(prev_year_row[fpi_col]) if fpi_col < len(prev_year_row) else None
            yoy = ((index_val - prev_val) / prev_val * 100) if index_val and prev_val and prev_val > 0 else None
            return {
                "index": index_val,
                "month": latest[date_col] if date_col < len(latest) else "",
                "yoy_change_pct": round(yoy, 1) if yoy is not None else None,
            }
    except Exception as e:
        logger.debug("ENERGY: FAO FPI fetch failed: %s", e)
        return {"error": str(e)}


async def _fetch_fertilizer_prices() -> Dict[str, Any]:
    """Fetch Urea/DAP prices from World Bank API (free, monthly)."""
    result: Dict[str, Any] = {"source": "world_bank"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for indicator, key in [(UREA_INDICATOR, "urea_price"), (DAP_INDICATOR, "dap_price")]:
                try:
                    resp = await client.get(
                        f"{WORLD_BANK_COMMODITIES_URL}/{indicator}",
                        params={"format": "json", "per_page": "2", "mrv": "1"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) and data[1]:
                            val = _safe_float(data[1][0].get("value"))
                            result[key] = val
                except Exception:
                    pass
    except Exception as e:
        logger.debug("ENERGY: fertilizer price fetch failed: %s", e)
        result["error"] = str(e)
    return result


def _compute_food_security_risk(
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    fertilizer: Dict[str, Any],
) -> float:
    """Score 0-100: high food prices / FAO FPI spike / fertilizer stress = risk."""
    base = 20.0
    # Food commodity spikes
    for c in food_commodities:
        raw = c.get("change_pct_raw")
        if raw is not None and abs(raw) > 10:
            base += 20
        elif raw is not None and abs(raw) > 5:
            base += 10
        elif raw is not None and abs(raw) > 3:
            base += 5
    # FAO FPI year-over-year change
    yoy = fao_fpi.get("yoy_change_pct")
    if yoy is not None:
        if yoy > 15:
            base += 25
        elif yoy > 10:
            base += 15
        elif yoy > 5:
            base += 8
    # Fertilizer prices (high = downstream food risk)
    urea = fertilizer.get("urea_price")
    dap = fertilizer.get("dap_price")
    if urea and urea > 400:
        base += 10
    if dap and dap > 700:
        base += 10
    return min(100.0, max(0.0, base))


def _compute_energy_score(commodities: List[Dict[str, Any]]) -> float:
    """Score 0–100: high commodity volatility = escalation risk."""
    base = 30.0
    # Commodity volatility: large moves = stress
    for c in commodities:
        raw = c.get("change_pct_raw")
        if raw is not None and abs(raw) > 10:
            base += 15
        elif raw is not None and abs(raw) > 5:
            base += 8
    return min(100.0, max(0.0, base))


# Threshold for "significant" oil move when linking to Iran/Hormuz global impact (percent)
GLOBAL_IMPACT_OIL_THRESHOLD_PCT = 2.0


def _build_summary(
    commodities: List[Dict[str, Any]],
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    score: float,
    food_risk: float,
    conflict: str = "",
) -> str:
    parts = []
    valid_c = [c for c in commodities if c.get("price") and "error" not in c]
    if valid_c:
        parts.append("Oil: " + ", ".join(f"{c.get('symbol', '')} {c.get('change_pct', '')}" for c in valid_c[:2]))
    valid_food = [c for c in food_commodities if c.get("price") and "error" not in c]
    if valid_food:
        parts.append("Food: " + ", ".join(f"{c.get('symbol', '')} {c.get('change_pct', '')}" for c in valid_food[:3]))
    fpi_val = fao_fpi.get("index")
    if fpi_val:
        yoy = fao_fpi.get("yoy_change_pct")
        yoy_str = f" ({yoy:+.1f}% YoY)" if yoy is not None else ""
        parts.append(f"FAO FPI: {fpi_val:.1f}{yoy_str}")
    if food_risk >= 60:
        parts.append(f"Food security risk: {food_risk:.0f}/100 (exposed: {', '.join(EXPOSED_COUNTRIES[:3])})")
    if not parts:
        return "ENERGY: No commodity data (set EIA_API_KEY/FRED_API_KEY for oil/food, or ALPHAVANTAGE_API_KEY)."
    out = "ENERGY: " + " ".join(parts)
    if conflict and "iran" in conflict.lower():
        max_up = max(
            (c.get("change_pct_raw") for c in valid_c if c.get("change_pct_raw") is not None),
            default=None,
        )
        if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
            out += " Global impact (Iran): Oil move may reflect Strait of Hormuz / chokepoint risk."
    return out


async def _generate_haiku_summary_energy(
    conflict: str,
    commodities: List[Dict[str, Any]],
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    energy_score: float,
    food_risk: float,
) -> Optional[str]:
    """Optional 2-3 sentence analyst summary via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary
        import json
        valid_c = [c for c in (commodities or []) if c.get("price") and "error" not in c]
        valid_food = [c for c in (food_commodities or []) if c.get("price") and "error" not in c]
        compact = {
            "conflict": conflict,
            "energy_score": energy_score,
            "food_security_risk": food_risk,
            "oil": [{"symbol": c.get("symbol"), "change_pct": c.get("change_pct")} for c in valid_c[:3]],
            "food": [{"symbol": c.get("symbol"), "change_pct": c.get("change_pct")} for c in valid_food[:3]],
            "fao_fpi_index": fao_fpi.get("index"),
            "fao_fpi_yoy": fao_fpi.get("yoy_change_pct"),
        }
        data = json.dumps(compact, indent=2)
        system = (
            "You are an energy and commodities analyst for conflict monitoring. Summarize the following "
            "data in 2-3 sentences: oil (Brent/WTI), food commodities, FAO Food Price Index, "
            "food security risk. Focus on escalation or chokepoint implications. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256)
        return out.strip() if out else None
    except Exception:
        return None


def _commodity_entry(
    symbol: str, label: str, price: float, prev_price: float, as_of: str
) -> Dict[str, Any]:
    """Build one commodity dict in the standard format."""
    change_pct = ((price - prev_price) / prev_price * 100) if prev_price and prev_price != 0 else None
    return {
        "symbol": symbol,
        "label": label,
        "price": f"{price:.2f}" if price else None,
        "change_pct": f"{change_pct:+.1f}%" if change_pct is not None else "0%",
        "change_pct_raw": change_pct,
        "as_of": as_of,
    }


async def _fetch_eia_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil (Brent, WTI) from EIA API v2 spot series. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    mapping = [(EIA_BRENT_SERIES, "BRENT", "Brent crude"), (EIA_WTI_SERIES, "WTI", "WTI crude")]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in mapping:
                try:
                    resp = await client.get(
                        f"{EIA_BASE}/{series_id}/data",
                        params={
                            "api_key": api_key.strip(),
                            "length": 5,
                            "sort[0][column]": "period",
                            "sort[0][direction]": "desc",
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    # EIA v2: response.data with period, value (strings)
                    records = (data.get("response") or {}).get("data") if isinstance(data, dict) else None
                    if not isinstance(records, list) or len(records) < 2:
                        continue
                    valid = [r for r in records if isinstance(r, dict) and r.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    period = latest.get("period") or latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, period))
                except Exception as e:
                    logger.debug("ENERGY: EIA series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: EIA oil fetch failed: %s", e)
    return results


async def _fetch_fred_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil (Brent, WTI) from FRED. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in FRED_OIL_SERIES:
                try:
                    resp = await client.get(
                        FRED_BASE,
                        params={
                            "series_id": series_id,
                            "api_key": api_key.strip(),
                            "file_type": "json",
                            "sort_order": "desc",
                            "limit": 5,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    obs = (data.get("observations") or []) if isinstance(data, dict) else []
                    valid = [o for o in obs if isinstance(o, dict) and o.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    as_of = latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, as_of))
                except Exception as e:
                    logger.debug("ENERGY: FRED oil series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: FRED oil fetch failed: %s", e)
    return results


async def _fetch_fred_food_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch food (Wheat, Corn, Soybean) from FRED monthly series. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in FRED_FOOD_SERIES:
                try:
                    resp = await client.get(
                        FRED_BASE,
                        params={
                            "series_id": series_id,
                            "api_key": api_key.strip(),
                            "file_type": "json",
                            "sort_order": "desc",
                            "limit": 5,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    obs = (data.get("observations") or []) if isinstance(data, dict) else []
                    valid = [o for o in obs if isinstance(o, dict) and o.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    as_of = latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, as_of))
                except Exception as e:
                    logger.debug("ENERGY: FRED food series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: FRED food fetch failed: %s", e)
    return results


async def _fetch_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil commodity quotes only (Brent, WTI) from Alpha Vantage."""
    return await _fetch_commodity_prices_for(api_key, OIL_SYMBOLS)


async def _fetch_food_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch food commodity quotes (Wheat, Corn, Soybean)."""
    return await _fetch_commodity_prices_for(api_key, FOOD_SYMBOLS)


async def _fetch_commodity_prices_for(
    api_key: str, symbols: List[tuple]
) -> List[Dict[str, Any]]:
    if not api_key:
        return []
    results = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for sym, label in symbols:
            try:
                resp = await client.get(
                    ALPHAVANTAGE_URL,
                    params={"function": sym, "interval": "daily", "apikey": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                series = data.get("data") or []
                if len(series) >= 2:
                    latest = series[0]
                    prev = series[1]
                    price = _safe_float(latest.get("value"))
                    prev_p = _safe_float(prev.get("value"))
                    change_pct = ((price - prev_p) / prev_p * 100) if prev_p and prev_p != 0 else None
                    results.append({
                        "symbol": sym,
                        "label": label,
                        "price": f"{price:.2f}" if price else None,
                        "change_pct": f"{change_pct:+.1f}%" if change_pct is not None else "0%",
                        "change_pct_raw": change_pct,
                        "as_of": latest.get("date", ""),
                    })
                else:
                    results.append({"symbol": sym, "label": label, "error": "Insufficient data"})
            except Exception as e:
                results.append({"symbol": sym, "label": label, "error": str(e)})
    return results


def run_energy_agent(conflict: str) -> Dict[str, Any]:
    """Run ENERGY/Commodities agent: oil/food prices (EIA/FRED/Alpha Vantage), FAO FPI, fertilizer."""
    eia_key = (os.getenv("EIA_API_KEY") or "").strip()
    fred_key = (os.getenv("FRED_API_KEY") or "").strip()
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")

    async def _run() -> Dict[str, Any]:
        fao_task = _fetch_fao_fpi()
        fert_task = _fetch_fertilizer_prices()

        # Oil: EIA first, then FRED, then Alpha Vantage
        oil_commodities: List[Dict[str, Any]] = []
        if eia_key:
            oil_commodities = await _fetch_eia_oil_prices(eia_key)
        if not oil_commodities and fred_key:
            oil_commodities = await _fetch_fred_oil_prices(fred_key)
        if not oil_commodities and av_key:
            oil_commodities = await _fetch_oil_prices(av_key)

        # Food: FRED first, then Alpha Vantage (resilient: failure must not drop whole result)
        food_commodities: List[Dict[str, Any]] = []
        try:
            if fred_key:
                food_commodities = await _fetch_fred_food_prices(fred_key)
            if not food_commodities and av_key:
                food_commodities = await _fetch_food_prices(av_key)
        except Exception as e:
            logger.warning("ENERGY: food commodities fetch failed, continuing without: %s", e)

        fao_fpi, fertilizer = await asyncio.gather(fao_task, fert_task)

        # Legacy: keep combined commodities for backward compat
        all_commodities = oil_commodities + food_commodities
        energy_score = _compute_energy_score(oil_commodities)
        food_risk = _compute_food_security_risk(food_commodities, fao_fpi, fertilizer)
        rule_summary = _build_summary(
            oil_commodities, food_commodities, fao_fpi,
            energy_score, food_risk, conflict=conflict,
        )
        try:
            llm_summary = await _generate_haiku_summary_energy(
                conflict, oil_commodities, food_commodities, fao_fpi, energy_score, food_risk,
            )
            summary = llm_summary if llm_summary else rule_summary
        except Exception as e:
            logger.debug("ENERGY: Haiku summary failed, using rule-based: %s", e)
            summary = rule_summary

        global_impact_note = None
        if conflict and "iran" in conflict.lower():
            valid_c = [c for c in oil_commodities if c.get("price") and "error" not in c and c.get("change_pct_raw") is not None]
            max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
            if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
                pct_str = f"{max_up:+.1f}%"
                global_impact_note = f"Brent/WTI {pct_str} – potential Hormuz chokepoint risk premium"
            # Also flag food security if relevant
            if food_risk >= 50 and not global_impact_note:
                global_impact_note = f"Food security risk {food_risk:.0f}/100 – chokepoint disruption threatens grain/fertilizer flows to {', '.join(EXPOSED_COUNTRIES[:3])}"
            elif food_risk >= 50 and global_impact_note:
                global_impact_note += f"; Food security risk {food_risk:.0f}/100"

        return {
            "energy_score": round(energy_score, 1),
            "agsi_storage": {"full": []},
            "commodities": oil_commodities,
            "food_commodities": food_commodities,
            "fao_fpi": fao_fpi,
            "fertilizer": fertilizer,
            "food_security_risk": round(food_risk, 1),
            "summary": summary,
            "global_impact_note": global_impact_note,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        source_results = [
            SourceResult(name="Oil (EIA/FRED/AV)", status="ok" if (out.get("commodities") or []) else "error", fetched_at=fetched_at, record_count=len(out.get("commodities") or [])),
            SourceResult(name="Food commodities", status="ok" if (out.get("food_commodities") or []) else "error", fetched_at=fetched_at, record_count=len(out.get("food_commodities") or [])),
            SourceResult(name="FAO FPI", status="ok" if (out.get("fao_fpi") and not out.get("fao_fpi", {}).get("error")) else "error", fetched_at=fetched_at),
            SourceResult(name="Fertilizer", status="ok" if (out.get("fertilizer") and not out.get("fertilizer", {}).get("error")) else "error", fetched_at=fetched_at),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "energy", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count >= 3 else "recent" if ok_count >= 2 else "stale" if ok_count >= 1 else "unavailable"
        meta = AgentMetadata(agent="energy", fetched_at=fetched_at, duration_ms=duration_ms, sources=source_results, confidence=confidence, data_freshness=data_freshness, fallback_used=False, error_summary=None)
        out["_meta"] = meta.model_dump(mode="json")
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(agent="energy", fetched_at=fetched_at, duration_ms=duration_ms, sources=[], confidence=compute_confidence_from_sources([]), data_freshness="unavailable", fallback_used=True, error_summary=str(e))
        return {
            "energy_score": 30.0,
            "agsi_storage": {"full": []},
            "commodities": [],
            "food_commodities": [],
            "fao_fpi": {},
            "fertilizer": {},
            "food_security_risk": 20.0,
            "summary": f"ENERGY error: {e}",
            "global_impact_note": None,
            "_meta": meta.model_dump(mode="json"),
        }
