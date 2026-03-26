"""
FININT Agent (orchestration only).

Fetching/parsing lives in fetchers/finint_fetchers.py.
Score computation lives in scorers/finint_scorer.py.
"""

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .fetchers.finint_fetchers import (
    get_brent_price as fetcher_get_brent_price,
    get_fear_greed as fetcher_get_fear_greed,
    get_gold_price as fetcher_get_gold_price,
    get_kalshi_conflict_markets as fetcher_get_kalshi_conflict_markets,
    get_metaculus_conflict_questions as fetcher_get_metaculus_conflict_questions,
    get_ofac_sanctions_highlights as fetcher_get_ofac_sanctions_highlights,
    get_polymarket_conflict_odds as fetcher_get_polymarket_conflict_odds,
    get_tracked_chain_wallets as fetcher_get_tracked_chain_wallets,
    get_tracked_wallet_positions as fetcher_get_tracked_wallet_positions,
    get_vix as fetcher_get_vix,
    get_wti_price as fetcher_get_wti_price,
)
from .health_registry import get_health_registry
from .llm import run_agent_with_fallback
from .scorers.finint_scorer import compute_finint_escalation_score
from .utils import ProcessingStep, ScoreConfidence, SourceResult, build_agent_meta, run_async, utc_now_iso


class OfacDelta(BaseModel):
    added_since_last_run: int = 0
    previous_total: int = 0
    current_total: int = 0


class FinintResult(BaseModel):
    brent: Dict[str, Any] = Field(default_factory=dict)
    wti: Dict[str, Any] = Field(default_factory=dict)
    gold: Dict[str, Any] = Field(default_factory=dict)
    vix: Dict[str, Any] = Field(default_factory=dict)
    fear_greed: Dict[str, Any] = Field(default_factory=dict)
    polymarket: List[Dict[str, Any]] = Field(default_factory=list)
    polymarket_fetched_at: Optional[str] = None
    metaculus: List[Dict[str, Any]] = Field(default_factory=list)
    metaculus_fetched_at: Optional[str] = None
    kalshi: List[Dict[str, Any]] = Field(default_factory=list)
    kalshi_fetched_at: Optional[str] = None
    ofac_sanctions: Dict[str, Any] = Field(default_factory=dict)
    ofac_delta: Optional[OfacDelta] = None
    tracked_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    tracked_wallets_fetched_at: Optional[str] = None
    tracked_chain_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    tracked_chain_wallets_fetched_at: Optional[str] = None
    escalation_score: float = 0.0
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=utc_now_iso)


def _run_rule_based_finint(conflict: str) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        brent = fetcher_get_brent_price()
        wti = fetcher_get_wti_price()
        gold = fetcher_get_gold_price()
        vix = fetcher_get_vix()
        fear_greed = fetcher_get_fear_greed()
        polymarket = fetcher_get_polymarket_conflict_odds(conflict)
        metaculus = fetcher_get_metaculus_conflict_questions(conflict)
        kalshi = fetcher_get_kalshi_conflict_markets(conflict)
        ofac = fetcher_get_ofac_sanctions_highlights(conflict)
        tracked_wallets = fetcher_get_tracked_wallet_positions()
        tracked_chain_wallets = fetcher_get_tracked_chain_wallets()

        score = compute_finint_escalation_score(
            brent=brent if isinstance(brent, dict) else {},
            vix=vix if isinstance(vix, dict) else {},
            fear_greed=fear_greed if isinstance(fear_greed, dict) else {},
            polymarket_list=[p for p in polymarket if isinstance(p, dict) and "error" not in p],
            metaculus_list=[m for m in metaculus if isinstance(m, dict) and "error" not in m],
            kalshi_list=[k for k in kalshi if isinstance(k, dict) and "error" not in k],
            ofac=ofac if isinstance(ofac, dict) else {},
        )

        sources_ok: List[str] = []
        sources_missing: List[str] = []
        for name, val in (
            ("brent", brent),
            ("wti", wti),
            ("gold", gold),
            ("vix", vix),
            ("fear_greed", fear_greed),
            ("polymarket", polymarket),
            ("metaculus", metaculus),
            ("kalshi", kalshi),
            ("ofac_sanctions", ofac),
            ("tracked_wallets", tracked_wallets),
            ("tracked_chain_wallets", tracked_chain_wallets),
        ):
            ok = bool(val) and not (isinstance(val, dict) and val.get("error"))
            if ok:
                sources_ok.append(name)
            else:
                sources_missing.append(name)

        score_confidence = ScoreConfidence(
            level="high" if len(sources_ok) >= 2 else "low",
            sources_ok=sources_ok,
            sources_missing=sources_missing,
        )

        result = FinintResult(
            brent=brent if isinstance(brent, dict) else {},
            wti=wti if isinstance(wti, dict) else {},
            gold=gold if isinstance(gold, dict) else {},
            vix=vix if isinstance(vix, dict) else {},
            fear_greed=fear_greed if isinstance(fear_greed, dict) else {},
            polymarket=[p for p in polymarket if isinstance(p, dict) and "error" not in p],
            metaculus=[m for m in metaculus if isinstance(m, dict) and "error" not in m],
            kalshi=[k for k in kalshi if isinstance(k, dict) and "error" not in k],
            ofac_sanctions=ofac if isinstance(ofac, dict) else {},
            tracked_wallets=[w for w in tracked_wallets if isinstance(w, dict)],
            tracked_chain_wallets=[w for w in tracked_chain_wallets if isinstance(w, dict)],
            escalation_score=round(score, 1),
            summary="FININT (rule-based): oil, gold, VIX, Fear & Greed, Polymarket, Metaculus, OFAC sanctions and wallet data.",
            score_confidence=score_confidence,
            fetched_at=fetched_at,
        )
        out = result.model_dump(mode="json")
        duration_ms = int((time.perf_counter() - start) * 1000)
        polymarket_raw = polymarket if isinstance(polymarket, list) else []
        polymarket_status = "ok"
        if any(isinstance(item, dict) and item.get("error") for item in polymarket_raw):
            polymarket_status = "error"
        elif len(polymarket_raw) == 0:
            # Empty market set is a soft degradation, not a hard source failure.
            polymarket_status = "degraded"

        source_results = [
            SourceResult(name="Brent", status=("ok" if "brent" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="WTI", status=("ok" if "wti" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="Gold", status=("ok" if "gold" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="VIX", status=("ok" if "vix" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="FearGreed", status=("ok" if "fear_greed" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="Polymarket", status=polymarket_status, fetched_at=fetched_at),
            SourceResult(name="Metaculus", status=("ok" if "metaculus" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="Kalshi", status=("ok" if "kalshi" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="OFAC", status=("ok" if "ofac_sanctions" in sources_ok else "error"), fetched_at=fetched_at),
            SourceResult(name="Wallets", status=("ok" if "tracked_wallets" in sources_ok else "error"), fetched_at=fetched_at),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "finint", sr)
        out["_meta"] = build_agent_meta(
            "finint",
            fetched_at,
            duration_ms,
            source_results,
            error_summary=(f"{len(sources_missing)} source(s) failed or missing" if sources_missing else None),
            has_any_data=bool(sources_ok),
            confidence=score_confidence,
            processing_steps=[ProcessingStep(step="fetch_financial_sources", at=fetched_at), ProcessingStep(step="compute_finint_score", at=fetched_at)],
        )
        return out
    except Exception as e:
        utc = utc_now_iso()
        return {
            "brent": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "wti": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "gold": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "vix": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "fear_greed": {"error": str(e), "fetched_at": utc},
            "polymarket": [],
            "metaculus": [],
            "kalshi": [],
            "ofac_sanctions": {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": utc},
            "tracked_wallets": [],
            "tracked_chain_wallets": [],
            "escalation_score": 50.0,
            "summary": f"FININT error: {e}",
            "score_confidence": {"level": "low", "sources_ok": [], "sources_missing": []},
            "fetched_at": utc,
        }


FININT_SYSTEM = """You are a FININT (Financial Intelligence) analyst.
Call all tools, compute escalation score (0-100), return ONLY valid JSON."""

_FININT_TOOL_FNS = {
    "get_brent_price": fetcher_get_brent_price,
    "get_wti_price": fetcher_get_wti_price,
    "get_gold_price": fetcher_get_gold_price,
    "get_polymarket_conflict_odds": fetcher_get_polymarket_conflict_odds,
    "get_metaculus_conflict_questions": fetcher_get_metaculus_conflict_questions,
    "get_ofac_sanctions_highlights": fetcher_get_ofac_sanctions_highlights,
    "get_tracked_wallet_positions": fetcher_get_tracked_wallet_positions,
    "get_tracked_chain_wallets": fetcher_get_tracked_chain_wallets,
}
_FININT_TOOL_SCHEMAS = [
    {"name": "get_brent_price", "description": "Fetch Brent crude oil price.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_wti_price", "description": "Fetch WTI crude oil price.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_gold_price", "description": "Fetch gold (XAU) price.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_polymarket_conflict_odds", "description": "Fetch Polymarket odds.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_metaculus_conflict_questions", "description": "Fetch Metaculus questions.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_ofac_sanctions_highlights", "description": "Fetch OFAC sanctions highlights.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_tracked_wallet_positions", "description": "Fetch tracked wallet positions.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_tracked_chain_wallets", "description": "Fetch tracked chain wallets.", "input_schema": {"type": "object", "properties": {}}},
]


def enrich_with_ner_entities(finint_result: Dict[str, Any], entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not entities:
        return finint_result
    ofac_data = finint_result.get("ofac_sanctions", {})
    ofac_sample = ofac_data.get("sample", [])
    ofac_names = {entry.get("name", "").lower().strip() for entry in ofac_sample if entry.get("name")}
    flagged: List[Dict[str, Any]] = []
    for ent in entities:
        ent_type = ent.get("type", "")
        if ent_type not in ("PERSON", "ORG"):
            continue
        ent_name = ent.get("entity", "").strip()
        if not ent_name:
            continue
        ent_lower = ent_name.lower()
        for ofac_name in ofac_names:
            if ent_lower in ofac_name or ofac_name in ent_lower:
                flagged.append({"entity": ent_name, "type": ent_type, "ofac_match": ofac_name, "context": ent.get("context", "")})
                break
    finint_result["ner_ofac_flags"] = flagged
    return finint_result


def run_finint_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return run_agent_with_fallback(
        conflict,
        rule_based_fn=_run_rule_based_finint,
        system_prompt=FININT_SYSTEM,
        user_content_template="Analyze financial indicators for conflict: {conflict}",
        tool_fns=_FININT_TOOL_FNS,
        tool_schemas=_FININT_TOOL_SCHEMAS,
    )
