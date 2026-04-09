"""
DIPLO / Legal Agent – orchestration only.
Fetchers and scoring logic are extracted to dedicated modules.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from .contracts import get_agent_fallback
from .fetchers.diplo_fetchers import fetch_eu_sanctions, fetch_ofac_sdn, fetch_un_icj_news
from .health_registry import get_health_registry
from .scorers.diplo_scorer import compute_diplo_score
from .utils import SourceResult, build_agent_meta, run_async, utc_now_iso


async def _generate_haiku_summary_diplo(
    conflict: str,
    ofac: Dict[str, Any],
    eu: Dict[str, Any],
    news: List[Dict[str, Any]],
    score: float,
) -> Optional[str]:
    """Optional 2-3 sentence analyst summary via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary
        import json

        compact = {
            "conflict": conflict,
            "diplo_score": score,
            "ofac_matches": ofac.get("total_matches"),
            "eu_mentions": eu.get("keyword_mentions"),
            "un_icj_news_count": len([n for n in news if n.get("title") and "error" not in n]),
            "news_categories": [n.get("diplo_category") for n in news if n.get("diplo_category")],
        }
        data = json.dumps(compact, indent=2)
        system = (
            "You are a sanctions and diplomatic analyst. Summarize the following DIPLO data "
            "in 2-3 sentences: OFAC SDN, EU sanctions, UN/ICJ news (and any categories like new_sanction, "
            "icj_ruling). Focus on escalation signals. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256, usage_agent="diplo")
        return out.strip() if out else None
    except Exception:
        return None


def _build_summary(ofac: Dict[str, Any], eu: Dict[str, Any], news: List[Dict[str, Any]], score: float) -> str:
    parts = []
    if ofac.get("total_matches"):
        parts.append(f"OFAC SDN: {ofac['total_matches']} conflict-relevant entries.")
    if ofac.get("error"):
        parts.append("OFAC: fetch failed.")
    if eu.get("keyword_mentions", 0) > 0:
        parts.append(f"EU sanctions: {eu['keyword_mentions']} keyword mentions.")
    valid_n = [n for n in news if n.get("title") and "error" not in n]
    if valid_n:
        parts.append(f"UN/ICJ: {len(valid_n)} relevant press items.")
    if not parts:
        return "DIPLO: No OFAC, EU sanctions, or UN/ICJ data available."
    return "DIPLO: " + " ".join(parts)


def run_diplo_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run DIPLO/Legal agent: OFAC SDN, EU sanctions, UN/ICJ RSS."""

    async def _run() -> Dict[str, Any]:
        ofac, eu, news = await asyncio.gather(
            fetch_ofac_sdn(conflict),
            fetch_eu_sanctions(conflict),
            fetch_un_icj_news(conflict),
        )
        diplo_score = compute_diplo_score(ofac, eu, news)
        rule_summary = _build_summary(ofac, eu, news, diplo_score)
        from .config import USE_DATA_ANALYST

        if USE_DATA_ANALYST:
            summary = rule_summary
        else:
            llm_summary = await _generate_haiku_summary_diplo(conflict, ofac, eu, news, diplo_score)
            summary = llm_summary if llm_summary else rule_summary
        return {
            "diplo_score": round(diplo_score, 1),
            "ofac_sdn": ofac,
            "eu_sanctions": eu,
            "un_icj_news": news,
            "summary": summary,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        ofac_ok = isinstance(out.get("ofac_sdn"), dict) and not out.get("ofac_sdn", {}).get("error")
        eu_ok = isinstance(out.get("eu_sanctions"), dict) and not out.get("eu_sanctions", {}).get("error")
        news_list = out.get("un_icj_news") or []
        news_ok = bool(news_list) and not (
            isinstance(news_list, list) and news_list and isinstance(news_list[0], dict) and news_list[0].get("error")
        )
        source_results = [
            SourceResult(
                name="OFAC SDN",
                status="ok" if ofac_ok else "error",
                fetched_at=fetched_at,
                record_count=out.get("ofac_sdn", {}).get("total_matches", 0) if ofac_ok else 0,
            ),
            SourceResult(name="EU sanctions", status="ok" if eu_ok else "error", fetched_at=fetched_at),
            SourceResult(
                name="UN/ICJ",
                status="ok" if news_ok else "error",
                fetched_at=fetched_at,
                record_count=len(news_list) if isinstance(news_list, list) else 0,
            ),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "diplo", sr)
        has_data = bool(out.get("diplo_score", 0) or out.get("ofac_sdn") or out.get("eu_sanctions") or out.get("un_icj_news"))
        out["_meta"] = build_agent_meta("diplo", fetched_at, duration_ms, source_results, has_any_data=has_data)
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fallback = get_agent_fallback("diplo")
        fallback["conflict"] = conflict
        fallback["summary"] = f"DIPLO error: {e}"
        fallback["_meta"] = build_agent_meta(
            "diplo",
            fetched_at,
            duration_ms,
            [],
            fallback_used=True,
            error_summary=str(e),
            has_any_data=False,
        )
        return fallback
