"""
ENERGY Agent orchestration.

Data fetching/parsing lives in fetchers/energy_fetchers.py.
Scoring/summary logic lives in scorers/energy_scorer.py.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .contracts import get_agent_fallback
from .fetchers.energy_fetchers import (
    _async_empty_wb,
    _fetch_eia_oil_prices,
    _fetch_fao_fpi,
    _fetch_fertilizer_prices,
    _fetch_food_prices,
    _fetch_fred_food_prices,
    _fetch_fred_oil_prices,
    _fetch_oil_prices,
    _fetch_world_bank_country_indicators,
    _world_bank_country_for_conflict,
)
from .health_registry import get_health_registry
from .scorers.energy_scorer import (
    build_energy_summary,
    build_global_impact_note,
    compute_energy_score,
    compute_food_security_risk,
)
from .utils import SourceResult, build_agent_meta, run_async, utc_now_iso

logger = logging.getLogger(__name__)


def _extract_inflation_cpi(wb_country: Optional[Dict[str, Any]]) -> tuple[Optional[float], Optional[str]]:
    if not isinstance(wb_country, dict):
        return None, None
    indicators = wb_country.get("indicators") or []
    for ind in indicators:
        if not isinstance(ind, dict):
            continue
        if ind.get("key") == "inflation_cpi_pct":
            val = ind.get("value")
            raw_date = str(ind.get("date") or "").strip()
            date_label: Optional[str] = None
            if raw_date:
                # WB macro is often yearly (e.g., "2024"); add month context from run.
                if len(raw_date) == 4 and raw_date.isdigit():
                    date_label = f"{raw_date}-01"
                else:
                    date_label = raw_date[:7]
            try:
                if val is None:
                    return None, date_label
                return float(val), date_label
            except (TypeError, ValueError):
                return None, date_label
    return None, None


async def _generate_haiku_summary_energy(
    conflict: str,
    commodities: List[Dict[str, Any]],
    food_commodities: List[Dict[str, Any]],
    fao_fpi: Dict[str, Any],
    energy_score: float,
    food_risk: float,
    wb_country: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    try:
        import json

        from services.haiku_service import analyst_summary

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
            "world_bank_country": wb_country if wb_country else {},
        }
        data = json.dumps(compact, indent=2)
        system = (
            "You are an energy and commodities analyst for conflict monitoring. Summarize the following "
            "data in 2-3 sentences: oil (Brent/WTI), food commodities, FAO Food Price Index, "
            "food security risk, and optional World Bank country macro (GDP growth, inflation, electricity access). "
            "Focus on escalation or chokepoint implications. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256, usage_agent="energy")
        return out.strip() if out else None
    except Exception:
        return None


def run_energy_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    eia_key = (os.getenv("EIA_API_KEY") or "").strip()
    fred_key = (os.getenv("FRED_API_KEY") or "").strip()
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")

    async def _run() -> Dict[str, Any]:
        fao_task = _fetch_fao_fpi()
        fert_task = _fetch_fertilizer_prices()

        oil_commodities: List[Dict[str, Any]] = []
        if eia_key:
            oil_commodities = await _fetch_eia_oil_prices(eia_key)
        if not oil_commodities and fred_key:
            oil_commodities = await _fetch_fred_oil_prices(fred_key)
        if not oil_commodities and av_key:
            oil_commodities = await _fetch_oil_prices(av_key)

        food_commodities: List[Dict[str, Any]] = []
        try:
            if fred_key:
                food_commodities = await _fetch_fred_food_prices(fred_key)
            if not food_commodities and av_key:
                food_commodities = await _fetch_food_prices(av_key)
        except Exception as e:
            logger.warning("ENERGY: food commodities fetch failed, continuing without: %s", e)

        wb_iso = _world_bank_country_for_conflict(conflict)
        wb_task = _fetch_world_bank_country_indicators(wb_iso) if wb_iso else _async_empty_wb()
        fao_fpi, fertilizer, wb_country = await asyncio.gather(fao_task, fert_task, wb_task)

        energy_score = compute_energy_score(oil_commodities)
        food_risk = compute_food_security_risk(food_commodities, fao_fpi, fertilizer)

        rule_summary = build_energy_summary(
            oil_commodities,
            food_commodities,
            fao_fpi,
            food_risk,
            conflict=conflict,
            wb_country=wb_country if wb_country else None,
        )

        try:
            llm_summary = await _generate_haiku_summary_energy(
                conflict,
                oil_commodities,
                food_commodities,
                fao_fpi,
                energy_score,
                food_risk,
                wb_country if wb_country else None,
            )
            summary = llm_summary if llm_summary else rule_summary
        except Exception as e:
            logger.debug("ENERGY: Haiku summary failed, using rule-based: %s", e)
            summary = rule_summary

        inflation_cpi_pct, inflation_date_label = _extract_inflation_cpi(wb_country if wb_country else None)
        return {
            "energy_score": round(energy_score, 1),
            "agsi_storage": {"full": []},
            "commodities": oil_commodities,
            "food_commodities": food_commodities,
            "fao_fpi": fao_fpi,
            "fertilizer": fertilizer,
            "world_bank_country": wb_country if wb_country else {},
            "food_security_risk": round(food_risk, 1),
            "summary": summary,
            "global_impact_note": build_global_impact_note(
                conflict,
                oil_commodities,
                food_risk,
                inflation_cpi_pct=inflation_cpi_pct,
                inflation_date_label=inflation_date_label,
            ),
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        source_results = [
            SourceResult(
                name="Oil (EIA/FRED/AV)",
                status="ok" if (out.get("commodities") or []) else "error",
                fetched_at=fetched_at,
                record_count=len(out.get("commodities") or []),
            ),
            SourceResult(
                name="Food commodities",
                status="ok" if (out.get("food_commodities") or []) else "error",
                fetched_at=fetched_at,
                record_count=len(out.get("food_commodities") or []),
            ),
            SourceResult(
                name="FAO FPI",
                status="ok" if (out.get("fao_fpi") and not out.get("fao_fpi", {}).get("error")) else "error",
                fetched_at=fetched_at,
            ),
            SourceResult(
                name="Fertilizer",
                status="ok" if (out.get("fertilizer") and not out.get("fertilizer", {}).get("error")) else "error",
                fetched_at=fetched_at,
            ),
            SourceResult(
                name="World Bank (country macro)",
                status="ok"
                if (
                    out.get("world_bank_country")
                    and out.get("world_bank_country", {}).get("indicators")
                    and not out.get("world_bank_country", {}).get("error")
                )
                else "error",
                fetched_at=fetched_at,
                record_count=len(out.get("world_bank_country", {}).get("indicators") or []),
            ),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "energy", sr)
        has_data = bool(
            (
                out.get("commodities")
                or out.get("food_commodities")
                or out.get("fao_fpi")
                or out.get("fertilizer")
                or (out.get("world_bank_country") or {}).get("indicators")
            )
        )
        out["_meta"] = build_agent_meta("energy", fetched_at, duration_ms, source_results, has_any_data=has_data)
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fallback = get_agent_fallback("energy")
        fallback["conflict"] = conflict
        fallback["summary"] = f"ENERGY error: {e}"
        fallback["_meta"] = build_agent_meta(
            "energy", fetched_at, duration_ms, [], fallback_used=True, error_summary=str(e), has_any_data=False
        )
        return fallback
