"""CEO-level synthesis: weighted scores, quality gate, LLM/rule-based findings, full API response."""

import logging
import os
from typing import Any, Dict, List

from calibration.dq_calibration import compute_calibration_metrics

from .ceo_config import CEO_LEGACY_AGENT_WEIGHTS, CEO_WEIGHTS
from .ceo_llm import run_ceo_llm_synthesis
from .ceo_prompt import build_supervisor_user_payload
from .ceo_response import (
    align_key_findings_confidence,
    assemble_ceo_response,
    build_provenance_index,
    build_rule_based_ceo_summary,
    heuristic_root_causes,
)
from .ceo_scoring import coerce_float, legacy_combined_excluding_degraded, threat_level_from_score
from .ceo_util import as_dict
from .dag_scheduler import ResultStore
from .division import DivisionHead, DivisionResult
from .dq_contract import apply_quality_to_all_agents
from .quality_gate import quality_gate_enabled, run_cross_agent_quality_gate
from .utils import get_analysis_run_id, infer_data_confidence_from_result

logger = logging.getLogger(__name__)


def _ceo_synthesize(conflict: str, divisions: List[DivisionHead], store: ResultStore) -> Dict[str, Any]:
    """CEO-level synthesis: weighted score, LLM or rule-based, full response."""
    division_results: Dict[str, DivisionResult] = {}
    for div in divisions:
        dr = store.get(f"{div.name}_summary")
        if isinstance(dr, DivisionResult):
            division_results[div.name] = dr

    total_weight = sum(CEO_WEIGHTS.get(d, 0) for d in division_results)
    if total_weight > 0:
        division_composite = sum(
            dr.score * (CEO_WEIGHTS.get(name, 0) / total_weight) for name, dr in division_results.items()
        )
    else:
        division_composite = 0.0

    agent_results = {
        name: as_dict(store.get(name))
        for name in [
            "finint",
            "sigint",
            "news",
            "geoint",
            "satintel",
            "socmint",
            "techint",
            "cyber",
            "energy",
            "protest",
            "diplo",
            "proximity",
            "narrative",
            "chokepoint",
        ]
    }
    pentagon_raw = as_dict(store.get("pentagon")) or {}
    agent_results["pentagon"] = pentagon_raw
    apply_quality_to_all_agents(agent_results)
    acled_refs = store.get("acled_refs") or []

    finint_result = agent_results.get("finint") or {}
    sigint_result = agent_results.get("sigint") or {}
    news_result = agent_results.get("news") or {}
    geoint_result = agent_results.get("geoint") or {}
    satintel_result = agent_results.get("satintel") or {}
    socmint_result = agent_results.get("socmint") or {}
    techint_result = agent_results.get("techint") or {}
    cyber_result = agent_results.get("cyber") or {}
    energy_result = agent_results.get("energy") or {}
    protest_result = agent_results.get("protest") or {}
    diplo_result = agent_results.get("diplo") or {}
    proximity_result = agent_results.get("proximity") or {}
    narrative_result = agent_results.get("narrative") or {}
    chokepoint_result = agent_results.get("chokepoint") or {}
    pentagon_result = agent_results.get("pentagon") or {}

    agent_data_confidence: Dict[str, str] = {
        name: infer_data_confidence_from_result(agent_results.get(name)) for name in CEO_LEGACY_AGENT_WEIGHTS
    }
    degraded_agents = sorted([n for n, c in agent_data_confidence.items() if c == "degraded"])

    finint_score = coerce_float(finint_result.get("escalation_score"), 0.0)
    sigint_score = coerce_float(sigint_result.get("sigint_score"), 0.0)
    news_score = coerce_float(news_result.get("news_score"), 0.0)
    geoint_score = coerce_float(geoint_result.get("geoint_score"), 0.0)
    satintel_score = coerce_float(satintel_result.get("satintel_score"), 0.0)
    socmint_score = coerce_float(socmint_result.get("socmint_score"), 0.0)
    techint_score = coerce_float(techint_result.get("techint_score"), 0.0)
    cyber_score = coerce_float(cyber_result.get("cyber_score"), 0.0)
    energy_score = coerce_float(energy_result.get("energy_score"), 0.0)
    protest_score = coerce_float(protest_result.get("protest_score"), 0.0)
    diplo_score = coerce_float(diplo_result.get("diplo_score"), 0.0)
    proximity_score = coerce_float(proximity_result.get("proximity_score"), 0.0)
    chokepoint_score = coerce_float(chokepoint_result.get("chokepoint_score"), 0.0)
    pentagon_score = coerce_float(pentagon_result.get("pentagon_score"), 0.0)

    scores_by_agent: Dict[str, float] = {
        "finint": finint_score,
        "sigint": sigint_score,
        "news": news_score,
        "geoint": geoint_score,
        "satintel": satintel_score,
        "socmint": socmint_score,
        "techint": techint_score,
        "cyber": cyber_score,
        "energy": energy_score,
        "protest": protest_score,
        "diplo": diplo_score,
        "proximity": proximity_score,
        "chokepoint": chokepoint_score,
        "pentagon": pentagon_score,
    }
    legacy_combined, legacy_active_weight = legacy_combined_excluding_degraded(scores_by_agent, agent_data_confidence)
    has_agent_scores = any(
        (
            "escalation_score" in finint_result,
            "sigint_score" in sigint_result,
            "news_score" in news_result,
            "geoint_score" in geoint_result,
            "satintel_score" in satintel_result,
            "socmint_score" in socmint_result,
            "techint_score" in techint_result,
            "cyber_score" in cyber_result,
            "energy_score" in energy_result,
            "protest_score" in protest_result,
            "diplo_score" in diplo_result,
            "proximity_score" in proximity_result,
            "chokepoint_score" in chokepoint_result,
            "pentagon_score" in pentagon_result,
        )
    )
    has_legacy_signal = has_agent_scores and legacy_active_weight > 0
    synthesis_score = legacy_combined if has_legacy_signal else division_composite

    qf = store.get("quality_fusion") or {}
    if not isinstance(qf, dict):
        qf = {}
    if quality_gate_enabled():
        data_quality_gate = run_cross_agent_quality_gate(
            conflict, agent_results, quality_fusion=qf, synthesis_score=synthesis_score
        )
    else:
        data_quality_gate = {
            "gate_version": 1,
            "quality_warnings": [],
            "gate_confidence": 0.0,
            "checks": {},
            "disabled": True,
        }

    agent_scores_for_predictive = {
        "finint": finint_score,
        "sigint": sigint_score,
        "news": news_score,
        "geoint": geoint_score,
        "satintel": satintel_score,
        "socmint": socmint_score,
        "techint": techint_score,
        "cyber": cyber_score,
        "energy": energy_score,
        "protest": protest_score,
        "diplo": diplo_score,
        "proximity": proximity_score,
        "chokepoint": chokepoint_score,
        "pentagon": pentagon_score,
    }

    temporal_context: Dict[str, Any] = {}
    try:
        from services.agent_score_history import get_temporal_context

        temporal_context = get_temporal_context(conflict, agent_scores_for_predictive)
    except ImportError:
        logger.debug("CEO: agent_score_history unavailable; temporal context disabled.")

    threat_level = threat_level_from_score(synthesis_score)

    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    key_findings: List[str] = []
    key_findings_context: List[str] = []
    key_findings_confidence: List[str] = []
    root_cause_suggestions: List[Dict[str, str]] = []
    scenarios: List[Any] = []
    summary = build_rule_based_ceo_summary(
        conflict, synthesis_score, threat_level, division_results, degraded_agents=degraded_agents
    )

    supervisor_payload = build_supervisor_user_payload(
        conflict,
        synthesis_score,
        threat_level,
        division_composite,
        division_results,
        acled_refs,
        agent_data_confidence,
        degraded_agents,
        finint_result,
        sigint_result,
        news_result,
        geoint_result,
        satintel_result,
        socmint_result,
        techint_result,
        cyber_result,
        energy_result,
        protest_result,
        diplo_result,
        proximity_result,
        narrative_result,
        chokepoint_result,
        pentagon_result,
        temporal_context,
        data_quality_gate,
    )

    if use_rule_based:
        for name, dr in sorted(division_results.items(), key=lambda x: -x[1].score):
            if dr.anomalies:
                for a in dr.anomalies:
                    key_findings.append(f"[{name}] {a.description}")
                    key_findings_confidence.append("medium")
        synthesis_meta: Dict[str, Any] = {"mode": "rule_based", "reason": "disabled_by_env"}
    else:
        synthesis_meta = {"mode": "rule_based", "reason": "llm_not_attempted"}
        agent_scores_list = [
            finint_score,
            sigint_score,
            news_score,
            geoint_score,
            satintel_score,
            socmint_score,
            techint_score,
            cyber_score,
            energy_score,
            protest_score,
            diplo_score,
            proximity_score,
            chokepoint_score,
            pentagon_score,
        ]
        key_findings, key_findings_context, key_findings_confidence, root_cause_suggestions, scenarios, summary, threat_level, synthesis_meta = run_ceo_llm_synthesis(
            summary=summary,
            threat_level=threat_level,
            key_findings=key_findings,
            key_findings_context=key_findings_context,
            key_findings_confidence=key_findings_confidence,
            root_cause_suggestions=root_cause_suggestions,
            scenarios=scenarios,
            supervisor_payload=supervisor_payload,
            agent_scores_list=agent_scores_list,
        )

    key_findings_confidence = align_key_findings_confidence(key_findings, key_findings_confidence)

    try:
        from .findings_builder import append_agent_findings

        all_agent_results = {k: as_dict(v) for k, v in store.all_results().items()}
        key_findings = append_agent_findings(
            key_findings,
            all_agent_results,
            conflict,
            chokepoint_score,
            key_findings_confidence,
        )
    except ImportError:
        logger.debug("CEO: findings_builder unavailable; skipping appended agent findings.")

    key_findings_confidence = align_key_findings_confidence(key_findings, key_findings_confidence)

    if len(key_findings_context) > len(key_findings):
        key_findings_context = key_findings_context[: len(key_findings)]

    if not root_cause_suggestions:
        root_cause_suggestions = heuristic_root_causes(energy_result, chokepoint_result)

    try:
        from .actor_model import build_actors_for_conflict

        actors = build_actors_for_conflict(conflict, key_findings)
    except Exception:
        actors = []

    try:
        from .predictive import build_predictive_block

        predictive = build_predictive_block(
            conflict, synthesis_score, agent_scores_for_predictive, degraded_agents=degraded_agents
        )
    except Exception:
        predictive = {}

    comp_result = store.get("compliance_build") or {}
    compliance = comp_result.get("compliance", {}) if isinstance(comp_result, dict) else {}
    alerts = comp_result.get("alerts", []) if isinstance(comp_result, dict) else []

    try:
        from .narrative_synthesis import synthesize_narrative

        narrative_story = synthesize_narrative(supervisor_payload)
    except Exception:
        narrative_story = ""

    provenance_index = build_provenance_index(agent_results)

    response = assemble_ceo_response(
        conflict=conflict,
        synthesis_score=synthesis_score,
        threat_level=threat_level,
        key_findings=key_findings,
        key_findings_context=key_findings_context,
        key_findings_confidence=key_findings_confidence,
        scenarios=scenarios,
        summary=summary,
        narrative_story=narrative_story,
        actors=actors,
        predictive=predictive,
        compliance=compliance,
        alerts=alerts,
        synthesis_meta=synthesis_meta,
        agent_data_confidence=agent_data_confidence,
        degraded_agents=degraded_agents,
        temporal_context=temporal_context,
        analysis_run_id=get_analysis_run_id(),
        provenance_index=provenance_index,
        qf=qf,
        data_quality_gate=data_quality_gate,
        store=store,
        division_results=division_results,
        as_dict_fn=as_dict,
    )

    try:
        from services.agent_score_history import record_daily_scores

        record_daily_scores(conflict, agent_scores_for_predictive)
    except (ImportError, OSError, ValueError, TypeError) as exc:
        logger.warning("CEO: failed to persist daily agent scores: %s", exc)

    try:
        response["dq_calibration_metrics"] = compute_calibration_metrics(response)
    except Exception:
        response["dq_calibration_metrics"] = {"calibration_schema_version": 1, "error": "compute_failed"}

    return response
