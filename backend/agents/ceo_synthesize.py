"""CEO-level synthesis: weighted scores, quality gate, LLM/rule-based findings, full API response."""

import logging
import os
from typing import Any, Dict, List

from calibration.dq_calibration import compute_calibration_metrics

from .ceo_config import CEO_LEGACY_AGENT_WEIGHTS, CEO_WEIGHTS
from .ceo_assessment import run_ceo_assessment
from .ceo_confidence_scoring import score_findings_confidence
from .ceo_llm import run_ceo_llm_synthesis
from .ceo_prompt import build_supervisor_user_payload
from .cross_agent_corroboration import apply_cross_agent_corroboration
from .ceo_response import (
    align_key_findings_confidence,
    assemble_ceo_response,
    build_provenance_index,
    build_rule_based_ceo_summary,
    heuristic_root_causes,
    normalize_next_steps,
)
from .ceo_scoring import coerce_float, legacy_combined_excluding_degraded, threat_level_from_score
from .ceo_util import as_dict
from .dag_scheduler import ResultStore
from .division import DivisionHead, DivisionResult
from .dq_contract import apply_quality_to_all_agents
from .finding_signal_gate import score_and_gate_findings
from .quality_gate import quality_gate_enabled, run_cross_agent_quality_gate
from .research_normalizer import apply_research_enrichments_from_raw
from .utils import get_analysis_run_id, infer_data_confidence_from_result, run_async

logger = logging.getLogger(__name__)


def _coerce_int_env(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except (TypeError, ValueError):
        return default


def _coerce_float_env(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except (TypeError, ValueError):
        return default


def _source_override_guardrail() -> Dict[str, Any]:
    """
    Parse SOURCE_STATUS_OVERRIDES and emit a synthesis warning when too many
    manual overrides are active (usually intended only for temporary incidents).
    """
    raw = (os.getenv("SOURCE_STATUS_OVERRIDES") or "").strip()
    if not raw:
        return {"active": False, "count": 0}
    entries = [p.strip() for p in raw.split(";") if p.strip()]
    parsed = []
    for e in entries:
        if "=" not in e:
            continue
        src, status = e.split("=", 1)
        src = src.strip()
        status = status.strip().lower()
        if not src:
            continue
        if status in ("ok", "degraded", "down", "error"):
            parsed.append((src, status))
    warn_min = max(1, _coerce_int_env("CEO_SOURCE_OVERRIDE_WARN_MIN", 3))
    return {
        "active": bool(parsed),
        "count": len(parsed),
        "warn": len(parsed) >= warn_min,
        "warn_min": warn_min,
        "sample": [f"{s}={st}" for s, st in parsed[:6]],
    }


def _build_trends_summary(temporal_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact trends block derived from services.agent_score_history.get_temporal_context().
    Always returns a dict (safe for UI consumption).
    """
    if not isinstance(temporal_context, dict):
        return {}
    agents = temporal_context.get("agents")
    if not isinstance(agents, dict):
        return {"as_of_utc_day": temporal_context.get("as_of_utc_day"), "top_movers": []}

    movers: List[Dict[str, Any]] = []
    for agent_key, row in agents.items():
        if not isinstance(row, dict):
            continue
        d = row.get("delta_vs_prior_utc_day")
        try:
            delta = float(d) if d is not None else None
        except (TypeError, ValueError):
            delta = None
        movers.append(
            {
                "agent": str(agent_key),
                "score_now": row.get("score_now"),
                "delta_vs_prior_utc_day": delta,
                "trend_7d": row.get("trend_7d"),
                "consecutive_days_up": row.get("consecutive_days_up"),
                "consecutive_days_down": row.get("consecutive_days_down"),
            }
        )

    def key_fn(x: Dict[str, Any]) -> float:
        v = x.get("delta_vs_prior_utc_day")
        return abs(float(v)) if isinstance(v, (int, float)) else -1.0

    movers_sorted = sorted(movers, key=key_fn, reverse=True)
    top_movers = [m for m in movers_sorted if isinstance(m.get("delta_vs_prior_utc_day"), (int, float))][:6]

    return {
        "as_of_utc_day": temporal_context.get("as_of_utc_day"),
        "prior_utc_day": temporal_context.get("prior_utc_day"),
        "top_movers": top_movers,
        "raw": temporal_context if len(top_movers) == 0 else {},
    }


def _build_anomalies_rollup(
    division_results: Dict[str, DivisionResult],
    temporal_context: Dict[str, Any],
    *,
    max_items: int = 10,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # 1) Division anomalies (already curated by each division head)
    for name, dr in sorted(division_results.items(), key=lambda x: -x[1].score):
        if not dr.anomalies:
            continue
        for a in dr.anomalies[:3]:
            out.append(
                {
                    "kind": "division_anomaly",
                    "source": str(name),
                    "description": getattr(a, "description", "") or "",
                    "severity": getattr(a, "severity", None),
                }
            )
            if len(out) >= max_items:
                return out

    # 2) Score-jump anomalies from temporal context (delta vs prior UTC day)
    agents = temporal_context.get("agents") if isinstance(temporal_context, dict) else None
    if isinstance(agents, dict):
        for agent_key, row in agents.items():
            if not isinstance(row, dict):
                continue
            d = row.get("delta_vs_prior_utc_day")
            try:
                delta = float(d) if d is not None else None
            except (TypeError, ValueError):
                delta = None
            if delta is None:
                continue
            if abs(delta) < 8.0:
                continue
            out.append(
                {
                    "kind": "score_jump",
                    "source": str(agent_key),
                    "description": f"Score moved {delta:+.1f} vs prior UTC day",
                    "delta_vs_prior_utc_day": round(delta, 2),
                    "score_now": row.get("score_now"),
                    "trend_7d": row.get("trend_7d"),
                }
            )
            if len(out) >= max_items:
                return out

    return out[:max_items]


def _build_implications(
    *,
    conflict: str,
    degraded_agents: List[str],
    data_quality_gate: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
    energy_result: Dict[str, Any],
    high_conf_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Deterministic implications layer (fallback-first). This should never be empty
    when there is any non-trivial signal, and should be cheap to compute.
    """
    out: List[Dict[str, Any]] = []

    def add(kind: str, title: str, rationale: str, confidence: str, *, refs: List[str] | None = None) -> None:
        if not title.strip():
            return
        out.append(
            {
                "kind": kind,
                "title": title.strip()[:180],
                "rationale": (rationale or "").strip()[:700],
                "confidence": confidence if confidence in ("high", "medium", "low") else "medium",
                "source_refs": refs or [],
            }
        )

    # Data quality implications
    qwarn = data_quality_gate.get("quality_warnings") if isinstance(data_quality_gate, dict) else None
    if isinstance(qwarn, list) and any(isinstance(w, str) and w.strip() for w in qwarn):
        add(
            "data_quality",
            "Assessment uncertainty elevated (quality warnings present)",
            "; ".join([str(w).strip() for w in qwarn if isinstance(w, str) and w.strip()][:3]),
            "medium",
        )
    if degraded_agents:
        stream_count = len(degraded_agents)
        stream_label = "stream" if stream_count == 1 else "streams"
        add(
            "data_gap",
            f"Degraded feeds may mask real escalation ({stream_count} {stream_label})",
            f"Degraded: {', '.join(degraded_agents[:8])}. Low scores can reflect missing data, not safety.",
            "high",
        )

    # Chokepoint implications
    cps = chokepoint_result.get("chokepoints") if isinstance(chokepoint_result, dict) else None
    if isinstance(cps, list):
        for cp in cps:
            if not isinstance(cp, dict):
                continue
            name = str(cp.get("name") or "").strip()
            risk = cp.get("disruption_risk")
            if not name or not isinstance(risk, (int, float)):
                continue
            if risk >= 65:
                add(
                    "risk",
                    f"High supply-chain disruption risk at {name}",
                    "Elevated disruption_risk suggests increased probability of delays/closures; corroborate with SIGINT/NEWS.",
                    "high",
                )
                break
            if risk >= 40:
                add(
                    "risk",
                    f"Moderate disruption risk at {name}",
                    "Risk premium likely; monitor for incident reporting and policy rhetoric escalation.",
                    "medium",
                )
                break

    # Energy/commodities implications
    commodities = energy_result.get("commodities") if isinstance(energy_result, dict) else None
    if isinstance(commodities, list):
        for c in commodities:
            if not isinstance(c, dict):
                continue
            sym = str(c.get("symbol") or "").upper().strip()
            ch = c.get("change_pct_raw")
            if sym and isinstance(ch, (int, float)) and abs(ch) >= 1.5:
                add(
                    "market",
                    f"{sym} moved {ch:+.1f}% (session)",
                    "Likely reflects changing risk premium; check chokepoints, shipping, and major incident reporting for causal linkage.",
                    "medium",
                )
                break

    # High-confidence finding implications (lightweight mapping)
    for row in high_conf_findings[:4]:
        if not isinstance(row, dict):
            continue
        finding = str(row.get("finding") or "").strip()
        if not finding:
            continue
        conf_val = row.get("confidence")
        conf = "high" if isinstance(conf_val, (int, float)) and conf_val >= 0.85 else "medium"
        add(
            "finding",
            f"So-what: {conflict}",
            finding,
            conf,
        )
        break

    # Ensure at least one implication when there is a conflict key
    if not out and conflict.strip():
        add("status", "No high-signal implications detected", "Signals appear stable or insufficient for inference.", "low")

    return out[:10]


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
            "mediaint",
            "techint",
            "cyber",
            "energy",
            "diplo",
            "proximity",
            "narrative",
            "chokepoint",
        ]
    }
    pentagon_raw = as_dict(store.get("pentagon")) or {}
    agent_results["pentagon"] = pentagon_raw
    research_enrichment = as_dict(store.get("research_enrichment")) or {}
    if isinstance(research_enrichment, dict):
        apply_research_enrichments_from_raw(agent_results, research_enrichment.get("enrichments_applied"))
    apply_quality_to_all_agents(agent_results)
    acled_refs = store.get("acled_refs") or []

    finint_result = agent_results.get("finint") or {}
    sigint_result = agent_results.get("sigint") or {}
    news_result = agent_results.get("news") or {}
    geoint_result = agent_results.get("geoint") or {}
    satintel_result = agent_results.get("satintel") or {}
    socmint_result = agent_results.get("socmint") or {}
    mediaint_result = agent_results.get("mediaint") or {}
    techint_result = agent_results.get("techint") or {}
    cyber_result = agent_results.get("cyber") or {}
    energy_result = agent_results.get("energy") or {}
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
    mediaint_score = coerce_float(mediaint_result.get("mediaint_score"), 0.0)
    techint_score = coerce_float(techint_result.get("techint_score"), 0.0)
    cyber_score = coerce_float(cyber_result.get("cyber_score"), 0.0)
    energy_score = coerce_float(energy_result.get("energy_score"), 0.0)
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
        "mediaint": mediaint_score,
        "techint": techint_score,
        "cyber": cyber_score,
        "energy": energy_score,
        "diplo": diplo_score,
        "proximity": proximity_score,
        "chokepoint": chokepoint_score,
        "pentagon": pentagon_score,
    }
    legacy_combined, legacy_active_weight = legacy_combined_excluding_degraded(scores_by_agent, agent_data_confidence)
    active_stream_count = len([k for k in CEO_LEGACY_AGENT_WEIGHTS if agent_data_confidence.get(k) != "degraded"])
    has_agent_scores = any(
        (
            "escalation_score" in finint_result,
            "sigint_score" in sigint_result,
            "news_score" in news_result,
            "geoint_score" in geoint_result,
            "satintel_score" in satintel_result,
            "socmint_score" in socmint_result,
            "mediaint_score" in mediaint_result,
            "techint_score" in techint_result,
            "cyber_score" in cyber_result,
            "energy_score" in energy_result,
            "diplo_score" in diplo_result,
            "proximity_score" in proximity_result,
            "chokepoint_score" in chokepoint_result,
            "pentagon_score" in pentagon_result,
        )
    )
    has_legacy_signal = has_agent_scores and legacy_active_weight > 0
    min_active_for_legacy = max(1, _coerce_int_env("CEO_MIN_ACTIVE_STREAMS_FOR_LEGACY_SCORE", 5))
    sparse_blend_division_weight = max(0.0, min(1.0, _coerce_float_env("CEO_SPARSE_STREAM_DIVISION_BLEND", 0.65)))
    if has_legacy_signal and active_stream_count >= min_active_for_legacy:
        synthesis_score = legacy_combined
        score_selection_meta: Dict[str, Any] = {
            "mode": "legacy_weighted",
            "active_stream_count": active_stream_count,
            "min_active_for_legacy": min_active_for_legacy,
        }
    elif has_legacy_signal:
        # Sparse-stream guardrail: keep legacy signal, but bias toward division stability.
        synthesis_score = (division_composite * sparse_blend_division_weight) + (
            legacy_combined * (1.0 - sparse_blend_division_weight)
        )
        score_selection_meta = {
            "mode": "blended_sparse_streams",
            "active_stream_count": active_stream_count,
            "min_active_for_legacy": min_active_for_legacy,
            "division_weight": sparse_blend_division_weight,
        }
    else:
        synthesis_score = division_composite
        score_selection_meta = {
            "mode": "division_fallback",
            "active_stream_count": active_stream_count,
            "min_active_for_legacy": min_active_for_legacy,
        }

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
        "mediaint": mediaint_score,
        "techint": techint_score,
        "cyber": cyber_score,
        "energy": energy_score,
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
    next_steps: List[Dict[str, Any]] = []
    root_cause_suggestions: List[Dict[str, str]] = []
    scenarios: List[Any] = []
    summary = build_rule_based_ceo_summary(
        conflict, synthesis_score, threat_level, division_results, degraded_agents=degraded_agents
    )

    # Optional stakeholder context: string persona or JSON dict via env.
    stakeholder_context: Dict[str, Any] | None = None
    raw_stakeholder = (os.getenv("CEO_STAKEHOLDER_CONTEXT") or "").strip()
    if raw_stakeholder:
        if raw_stakeholder.lstrip().startswith("{"):
            try:
                import json

                parsed = json.loads(raw_stakeholder)
                stakeholder_context = parsed if isinstance(parsed, dict) else {"persona": "general"}
            except Exception:
                stakeholder_context = {"persona": raw_stakeholder}
        else:
            stakeholder_context = {"persona": raw_stakeholder}

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
        mediaint_result,
        techint_result,
        cyber_result,
        energy_result,
        diplo_result,
        proximity_result,
        narrative_result,
        chokepoint_result,
        pentagon_result,
        temporal_context,
        data_quality_gate,
        stakeholder_context,
    )

    # Pre-synthesis noise reduction: score cross-stream finding candidates and gate them.
    finding_gate: Dict[str, Any] = {"accepted": [], "archived": [], "recovered": [], "meta": {"disabled": True}}
    try:
        from .findings_builder import collect_agent_finding_candidates

        candidates = collect_agent_finding_candidates(
            {**agent_results, "acled_refs": acled_refs},
            conflict=conflict,
            chokepoint_score=chokepoint_score,
        )
        candidates, corroboration_meta = apply_cross_agent_corroboration(candidates)
        gate_threshold = float(os.getenv("FINDING_SIGNAL_GATE_THRESHOLD", "0.7"))
        finding_gate = run_async(
            score_and_gate_findings(
                candidates=candidates,
                conflict=conflict,
                threshold=gate_threshold,
                max_llm=int(os.getenv("FINDING_SIGNAL_GATE_MAX_LLM", "20")),
            )
        )
        accepted_rows = finding_gate.get("accepted") if isinstance(finding_gate.get("accepted"), list) else []
        archived_rows = finding_gate.get("archived") if isinstance(finding_gate.get("archived"), list) else []
        min_accepted = max(0, _coerce_int_env("FINDING_SIGNAL_GATE_MIN_ACCEPTED", 3))
        recover_min_total = max(0.0, min(1.0, _coerce_float_env("FINDING_SIGNAL_GATE_RECOVER_MIN_TOTAL", 0.55)))
        recovered_rows: List[Dict[str, Any]] = []
        if len(accepted_rows) < min_accepted and archived_rows:
            deficit = min_accepted - len(accepted_rows)
            for row in archived_rows:
                if not isinstance(row, dict):
                    continue
                try:
                    total = float(row.get("total") or 0.0)
                except (TypeError, ValueError):
                    total = 0.0
                if total < recover_min_total:
                    continue
                recovered_rows.append(row)
                if len(recovered_rows) >= deficit:
                    break
        finding_gate["recovered"] = recovered_rows
        finding_gate_meta = finding_gate.get("meta") if isinstance(finding_gate.get("meta"), dict) else {}
        finding_gate["meta"] = {
            **finding_gate_meta,
            "min_accepted_target": min_accepted,
            "recovered_count": len(recovered_rows),
            "recover_min_total": recover_min_total,
            "was_restrictive": bool(len(accepted_rows) < min_accepted and len(archived_rows) > 0),
        }
        supervisor_payload["finding_signal_gate"] = {
            "threshold": gate_threshold,
            "accepted": [f.get("text") for f in (finding_gate.get("accepted") or [])[:12] if isinstance(f, dict)],
            "archived_count": len(finding_gate.get("archived") or []),
            "recovered_count": len(finding_gate.get("recovered") or []),
            "meta": finding_gate.get("meta") or {},
        }
        supervisor_payload["cross_agent_corroboration"] = corroboration_meta
    except Exception as e:
        supervisor_payload["finding_signal_gate"] = {"disabled": True, "error": str(e)[:180]}

    if use_rule_based:
        for name, dr in sorted(division_results.items(), key=lambda x: -x[1].score):
            if dr.anomalies:
                for a in dr.anomalies:
                    key_findings.append(f"[{name}] {a.description}")
                    key_findings_confidence.append("medium")
        # Minimal deterministic action block (keeps output useful without LLM).
        prov_refs: List[str] = []
        for ag in agent_results.values():
            if isinstance(ag, dict):
                for u in (ag.get("provenance_refs") or [])[:3]:
                    if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                        prov_refs.append(u.strip())
            if len(prov_refs) >= 10:
                break
        prov_refs = list(dict.fromkeys(prov_refs))[:6]
        next_steps = [
            {
                "action": "Verify top escalatory claims against primary/credible sources.",
                "owner": "analyst",
                "time_horizon": "now",
                "why": "Rule-based synthesis: reduce narrative noise and false positives.",
                "source_refs": prov_refs,
                "confidence": "medium",
            },
            {
                "action": "Set/confirm alert rules for sudden score jumps (multi-stream corroboration required).",
                "owner": "ops",
                "time_horizon": "24h",
                "why": "Catch real shifts while limiting single-stream spikes.",
                "source_refs": [],
                "confidence": "medium",
            },
        ]
        if degraded_agents:
            next_steps.append(
                {
                    "action": f"Repair degraded data feeds and re-run analysis (degraded: {', '.join(degraded_agents[:6])}).",
                    "owner": "ops",
                    "time_horizon": "24h",
                    "why": "Low scores can reflect missing data, not safety.",
                    "source_refs": [],
                    "confidence": "high",
                }
            )
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
            mediaint_score,
            techint_score,
            cyber_score,
            energy_score,
            diplo_score,
            proximity_score,
            chokepoint_score,
            pentagon_score,
        ]
        (
            key_findings,
            key_findings_context,
            key_findings_confidence,
            next_steps,
            root_cause_suggestions,
            scenarios,
            summary,
            threat_level,
            synthesis_meta,
        ) = run_ceo_llm_synthesis(
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
    next_steps = normalize_next_steps(next_steps)

    # Replace "append everything" with gated append + soft recovery from near-threshold rows.
    try:
        accepted = finding_gate.get("accepted") or []
        recovered = finding_gate.get("recovered") or []
        archived = finding_gate.get("archived") or []
        ranked_rows = [r for r in [*accepted, *recovered] if isinstance(r, dict) and r.get("text")]
        ranked_texts = [a.get("text") for a in ranked_rows if isinstance(a.get("text"), str)]
        existing = {str(k).strip() for k in key_findings if isinstance(k, str)}
        appended = 0
        min_key_findings = max(1, _coerce_int_env("CEO_MIN_KEY_FINDINGS", 6))
        base_append_max = max(1, _coerce_int_env("FINDING_SIGNAL_GATE_APPEND_MAX", 3))
        append_cap = max(base_append_max, _coerce_int_env("FINDING_SIGNAL_GATE_APPEND_MAX_CAP", 8))
        deficit = max(0, min_key_findings - len(key_findings))
        append_budget = min(append_cap, max(base_append_max, base_append_max + deficit))
        for t in ranked_texts:
            if t in existing:
                continue
            key_findings.append(t)
            total = 0.0
            for a in ranked_rows:
                if isinstance(a, dict) and a.get("text") == t:
                    try:
                        total = float(a.get("total") or 0.0)
                    except (TypeError, ValueError):
                        total = 0.0
                    break
            lv = "high" if total >= 0.85 else "medium" if total >= 0.7 else "low"
            key_findings_confidence.append(lv)
            appended += 1
            if appended >= append_budget:
                break

        # Hard floor: if we still have too few findings, backfill from top archived rows.
        if len(key_findings) < min_key_findings:
            for row in archived:
                if not isinstance(row, dict):
                    continue
                t = row.get("text")
                if not isinstance(t, str) or not t.strip() or t in existing:
                    continue
                try:
                    total = float(row.get("total") or 0.0)
                except (TypeError, ValueError):
                    total = 0.0
                key_findings.append(t)
                lv = "medium" if total >= 0.65 else "low"
                key_findings_confidence.append(lv)
                existing.add(t)
                if len(key_findings) >= min_key_findings:
                    break
    except Exception:
        pass

    key_findings_confidence = align_key_findings_confidence(key_findings, key_findings_confidence)

    if len(key_findings_context) > len(key_findings):
        key_findings_context = key_findings_context[: len(key_findings)]

    # So-what layer: stakeholder-specific assessment from high-confidence findings.
    # Step A: (cheap) 3D confidence scoring (default: Haiku) on synthesized findings.
    findings_for_scoring: List[Dict[str, Any]] = []
    for i, f in enumerate(key_findings[:25]):
        c = (key_findings_confidence[i] if i < len(key_findings_confidence) else "medium") or "medium"
        ctx = key_findings_context[i] if i < len(key_findings_context) else ""
        findings_for_scoring.append({"finding": f, "confidence": str(c).lower(), "context": ctx})

    confidence_scoring = score_findings_confidence(
        conflict=conflict,
        findings=findings_for_scoring,
        provenance_urls=supervisor_payload.get("provenance_urls") or [],
        stakeholder=stakeholder_context or supervisor_payload.get("stakeholder") or {},
    )

    # Step B: filter to high-confidence findings for the (expensive) Sonnet assessment.
    conf_threshold = float(os.getenv("CEO_ASSESSMENT_CONFIDENCE_THRESHOLD", "0.7"))
    high_conf_findings: List[Dict[str, Any]] = []
    for row in (confidence_scoring.get("scores") or [])[:25]:
        if not isinstance(row, dict):
            continue
        try:
            overall = float(row.get("overall_confidence") or 0.0)
        except (TypeError, ValueError):
            overall = 0.0
        if overall < conf_threshold:
            continue
        finding = str(row.get("finding") or "").strip()
        if not finding:
            continue
        high_conf_findings.append(
            {
                "finding": finding,
                "confidence": overall,
                "dimensions": row.get("dimensions") or {},
                "rationale": row.get("rationale") or "",
            }
        )
    if not high_conf_findings and findings_for_scoring:
        # Never feed an empty payload; fall back to top 3 (even if below threshold).
        for f in findings_for_scoring[:3]:
            high_conf_findings.append(
                {"finding": f.get("finding") or "", "confidence": 0.65, "dimensions": {}, "rationale": ""}
            )

    assessment = run_ceo_assessment(
        conflict=conflict,
        supervisor_payload=supervisor_payload,
        high_conf_findings=high_conf_findings,
        summary=summary,
        stakeholder_context=stakeholder_context,
    )

    # Implications-first analysis blocks (fallback-first, additive)
    trends = _build_trends_summary(temporal_context)
    anomalies_rollup = _build_anomalies_rollup(division_results, temporal_context)
    implications = _build_implications(
        conflict=conflict,
        degraded_agents=degraded_agents,
        data_quality_gate=data_quality_gate,
        chokepoint_result=chokepoint_result,
        energy_result=energy_result,
        high_conf_findings=high_conf_findings,
    )

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

    briefing_interpretation = ""
    briefing_interpretation_meta: Dict[str, Any] = {}
    try:
        from .narrative_synthesis import synthesize_briefing_interpretation

        briefing_interpretation, briefing_interpretation_meta = synthesize_briefing_interpretation(
            conflict=conflict,
            summary=summary or "",
            threat_level=threat_level or "",
            escalation_score=float(synthesis_score),
            key_findings=key_findings,
            scenarios=scenarios,
            implications=implications,
            trends=trends,
            anomalies_rollup=anomalies_rollup,
            narrative_story=narrative_story or "",
            assessment=assessment if isinstance(assessment, dict) else {},
            degraded_agents=degraded_agents,
        )
    except Exception:
        briefing_interpretation = ""
        briefing_interpretation_meta = {"mode": "error", "model": None}

    provenance_index = build_provenance_index(agent_results)

    response = assemble_ceo_response(
        conflict=conflict,
        synthesis_score=synthesis_score,
        threat_level=threat_level,
        key_findings=key_findings,
        key_findings_context=key_findings_context,
        key_findings_confidence=key_findings_confidence,
        next_steps=next_steps,
        scenarios=scenarios,
        summary=summary,
        narrative_story=narrative_story,
        briefing_interpretation=briefing_interpretation,
        actors=actors,
        predictive=predictive,
        compliance=compliance,
        alerts=alerts,
        implications=implications,
        trends=trends,
        anomalies_rollup=anomalies_rollup,
        synthesis_meta=synthesis_meta,
        agent_data_confidence=agent_data_confidence,
        degraded_agents=degraded_agents,
        temporal_context=temporal_context,
        analysis_run_id=get_analysis_run_id(),
        provenance_index=provenance_index,
        qf=qf,
        data_quality_gate=data_quality_gate,
        research_enrichment=research_enrichment if isinstance(research_enrichment, dict) else {},
        store=store,
        division_results=division_results,
        as_dict_fn=as_dict,
    )
    source_override_meta = _source_override_guardrail()
    synthesis_meta = {
        **(synthesis_meta if isinstance(synthesis_meta, dict) else {}),
        "score_selection": score_selection_meta,
        "finding_gate_recovery": {
            "accepted_n": len(finding_gate.get("accepted") or []),
            "recovered_n": len(finding_gate.get("recovered") or []),
            "archived_n": len(finding_gate.get("archived") or []),
        },
    }
    if source_override_meta.get("warn"):
        synthesis_meta["source_overrides_warning"] = {
            "message": "Multiple SOURCE_STATUS_OVERRIDES are active; this can suppress findings and understate confidence.",
            "count": source_override_meta.get("count"),
            "sample": source_override_meta.get("sample"),
        }
    response["synthesis_meta"] = synthesis_meta
    response["assessment"] = assessment
    response["confidence_scoring"] = confidence_scoring
    if briefing_interpretation_meta:
        response["briefing_interpretation_meta"] = briefing_interpretation_meta

    # Low-confidence archive: keep gated-out findings available for later search/inspection.
    # This is additive to the API response (backwards-compatible).
    try:
        response["low_confidence_archive"] = {
            "finding_signal_gate": {
                "meta": finding_gate.get("meta") or {},
                "archived": (finding_gate.get("archived") or [])[:50],
                "accepted": (finding_gate.get("accepted") or [])[:20],
            }
        }
    except Exception:
        response["low_confidence_archive"] = {"finding_signal_gate": {"error": "unavailable"}}

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
