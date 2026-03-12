"""
ENERGY / Commodities Agent – Gas storage (AGSI+), commodity indices, optional FAO/Comtrade.
Fetches: EU gas storage (AGSI+), optional commodity prices (Alpha Vantage), humanitarian/price indices.
Rule-based score from storage levels and price volatility. No LLM.
"""
import asyncio
import os
from typing import Any, Dict, List

import httpx

from .utils import run_async

# AGSI+ API (free with registration) – EU gas storage
AGSI_BASE = "https://agsi.gie.eu/api"
ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"

# Commodity symbols for conflict-relevant markets (Alpha Vantage: function name, label)
COMMODITY_SYMBOLS = [
    ("BRENT", "Brent crude"),
    ("WTI", "WTI crude"),
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _fetch_agsi_storage(api_key: str) -> Dict[str, Any]:
    """Fetch EU gas storage data from AGSI+ (optional AGSI_API_KEY)."""
    if not api_key or not api_key.strip():
        return {"full": [], "error": "AGSI_API_KEY not set"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # EU aggregate and key countries (Germany, Italy, etc.)
            resp = await client.get(
                f"{AGSI_BASE}/",
                params={"limit": 100},
                headers={"x-key": api_key.strip()},
            )
            resp.raise_for_status()
            data = resp.json()
        # AGSI returns { "data": [...], "gas_day": "..." }
        records = data.get("data") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        by_country: Dict[str, Dict] = {}
        for r in records if isinstance(records, list) else []:
            if not isinstance(r, dict):
                continue
            country = r.get("country") or r.get("name") or "EU"
            full_pct = _safe_float(r.get("full") or r.get("fullPercentage"), 0)
            by_country[country] = {
                "country": country,
                "full_pct": full_pct,
                "gas_in_storage": r.get("gasInStorage"),
                "trend": r.get("trend"),
            }
        return {"full": list(by_country.values())[:15], "error": None}
    except Exception as e:
        return {"full": [], "error": str(e)}


async def _fetch_commodity_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch commodity quotes from Alpha Vantage (reuse ALPHAVANTAGE_API_KEY)."""
    if not api_key:
        return []
    results = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for sym, label in COMMODITY_SYMBOLS:
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


def _compute_energy_score(agsi: Dict[str, Any], commodities: List[Dict[str, Any]]) -> float:
    """Score 0–100: low storage or high volatility = escalation risk."""
    base = 30.0
    # AGSI: low EU storage = higher risk
    full_list = agsi.get("full") or []
    if full_list:
        avg_full = sum(_safe_float(x.get("full_pct")) for x in full_list) / max(len(full_list), 1)
        if avg_full < 50:
            base += 25
        elif avg_full < 70:
            base += 12
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
    agsi: Dict[str, Any], commodities: List[Dict[str, Any]], score: float, conflict: str = ""
) -> str:
    parts = []
    if agsi.get("full"):
        parts.append(f"AGSI+: {len(agsi['full'])} storage record(s).")
    elif agsi.get("error"):
        parts.append("AGSI+: not available (set AGSI_API_KEY for EU gas storage).")
    valid_c = [c for c in commodities if c.get("price") and "error" not in c]
    if valid_c:
        parts.append("Commodities: " + ", ".join(f"{c.get('symbol', '')} {c.get('change_pct', '')}" for c in valid_c[:3]))
    if not parts:
        return "ENERGY: No AGSI or commodity data (set AGSI_API_KEY and/or ALPHAVANTAGE_API_KEY)."
    out = "ENERGY: " + " ".join(parts)
    # Global impact (Iran): link oil move to Strait of Hormuz / chokepoint risk when relevant
    if conflict and "iran" in conflict.lower():
        max_up = max(
            (c.get("change_pct_raw") for c in valid_c if c.get("change_pct_raw") is not None),
            default=None,
        )
        if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
            out += " Global impact (Iran): Oil move may reflect Strait of Hormuz / chokepoint risk."
    return out


def run_energy_agent(conflict: str) -> Dict[str, Any]:
    """Run ENERGY/Commodities agent: AGSI+ gas storage, optional commodity prices."""
    agsi_key = os.getenv("AGSI_API_KEY")
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")

    async def _run() -> Dict[str, Any]:
        agsi = await _fetch_agsi_storage(agsi_key or "")
        commodities = await _fetch_commodity_prices(av_key) if av_key else []
        energy_score = _compute_energy_score(agsi, commodities)
        summary = _build_summary(agsi, commodities, energy_score, conflict=conflict)
        global_impact_note = None
        if conflict and "iran" in conflict.lower():
            valid_c = [c for c in commodities if c.get("price") and "error" not in c and c.get("change_pct_raw") is not None]
            max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
            if max_up is not None and max_up >= GLOBAL_IMPACT_OIL_THRESHOLD_PCT:
                pct_str = f"{max_up:+.1f}%"
                global_impact_note = f"Brent/WTI {pct_str} – potential Hormuz chokepoint risk premium"
        return {
            "energy_score": round(energy_score, 1),
            "agsi_storage": agsi,
            "commodities": commodities,
            "summary": summary,
            "global_impact_note": global_impact_note,
        }

    try:
        return run_async(_run())
    except Exception as e:
        return {
            "energy_score": 30.0,
            "agsi_storage": {"full": [], "error": str(e)},
            "commodities": [],
            "summary": f"ENERGY error: {e}",
            "global_impact_note": None,
        }
