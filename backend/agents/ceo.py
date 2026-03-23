"""
CEO Orchestrator – Final DAG-Node (Tier 5: ceo_synthesis).

Reads all 5 Division-Summaries from the ResultStore, computes the weighted
composite score, builds a delta-aware LLM prompt, and produces the final
assessment. Preserves the API response format for backwards compatibility.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .agent_state_store import get_agent_state_store
from .context import WAVE1_AGENTS, WAVE2_AGENTS, AgentContext, build_context_from_results
from .dag_scheduler import DAGNode, DAGScheduler, ResultStore, ResultStoreManager
from .division import DivisionHead, DivisionResult
from .divisions import (
    FinancialDivision,
    InformationDivision,
    MilitaryDivision,
    PoliticalDivision,
    TechnicalDivision,
)
from .entity_registry import EntityRegistry
from .registry import AgentRegistry, get_agent_registry
from .utils import infer_data_confidence_from_result

logger = logging.getLogger(__name__)

# Legacy supervisor: per-agent weights (sum 1.0). Excluded when data_confidence=degraded (renormalized).
CEO_LEGACY_AGENT_WEIGHTS: Dict[str, float] = {
    "finint": 0.09,
    "sigint": 0.11,
    "news": 0.09,
    "geoint": 0.05,
    "satintel": 0.05,
    "socmint": 0.08,
    "techint": 0.07,
    "cyber": 0.07,
    "energy": 0.07,
    "protest": 0.07,
    "diplo": 0.06,
    "proximity": 0.08,
    "chokepoint": 0.10,
}

# CEO-level division weights
CEO_WEIGHTS = {
    "military": 0.30,
    "financial": 0.18,
    "information": 0.22,
    "political": 0.14,
    "technical": 0.16,
}

_MAX_PAYLOAD_CHARS = 250_000


def _normalize_finding_confidence(val: Any) -> str:
    s = str(val).strip().lower()
    if s in ("high", "h", "3"):
        return "high"
    if s in ("low", "l", "1"):
        return "low"
    return "medium"


def _legacy_combined_excluding_degraded(
    scores: Dict[str, float],
    agent_data_confidence: Dict[str, str],
) -> Tuple[float, float]:
    """Weighted mean over non-degraded agents; weights renormalized to sum to 1.

    Returns (combined_score, active_weight_sum). If active_weight_sum==0, all streams are degraded.
    """
    active = {
        k: w
        for k, w in CEO_LEGACY_AGENT_WEIGHTS.items()
        if agent_data_confidence.get(k) != "degraded"
    }
    if not active:
        return 0.0, 0.0
    tw = sum(active.values())
    combined = sum(scores.get(k, 0.0) * (active[k] / tw) for k in active)
    return combined, tw


def _degraded_streams_caveat(degraded_agents: List[str]) -> str:
    labels = ", ".join(a.upper() for a in degraded_agents)
    return (
        f"Data caveat: degraded streams (no reliable feed) for {labels} — "
        "treat those scores as unknown; low values reflect missing data, not evidence of safety."
    )


def _align_key_findings_confidence(findings: List[str], conf: List[str]) -> List[str]:
    """Pad or trim confidence list to match key_findings length (default medium)."""
    out = list(conf[: len(findings)])
    while len(out) < len(findings):
        out.append("medium")
    return out


def _normalize_root_cause_suggestions(raw: Any) -> List[Dict[str, str]]:
    """Parse CEO JSON root_cause_suggestions: list of objects or 'signal → cause' strings."""
    out: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:8]:
        if isinstance(item, str):
            s = item.strip()
            sep = "→" if "→" in s else ("->" if "->" in s else "")
            if sep:
                parts = s.split(sep, 1)
                signal = parts[0].strip()
                likely = parts[1].strip() if len(parts) > 1 else ""
                if signal and likely:
                    out.append({"signal": signal, "likely_cause": likely, "confidence": "medium"})
            continue
        if isinstance(item, dict):
            sig = str(item.get("signal") or item.get("observation") or "").strip()
            cause = str(item.get("likely_cause") or item.get("cause") or item.get("driver") or "").strip()
            conf = str(item.get("confidence") or "medium").strip().lower()
            if conf not in ("high", "medium", "low"):
                conf = "medium"
            if sig and cause:
                out.append({"signal": sig, "likely_cause": cause, "confidence": conf})
    return out[:6]


def _heuristic_root_causes(
    energy_result: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Deterministic hypotheses when the LLM omits root_cause_suggestions."""
    out: List[Dict[str, str]] = []
    seen_sig: set[str] = set()

    def add(signal: str, likely_cause: str, confidence: str) -> None:
        if signal in seen_sig:
            return
        seen_sig.add(signal)
        out.append({"signal": signal, "likely_cause": likely_cause, "confidence": confidence})

    note = energy_result.get("global_impact_note")
    if isinstance(note, str) and note.strip():
        lower = note.lower()
        if any(x in lower for x in ("hormuz", "chokepoint", "brent", "wti", "strait")):
            add("Elevated oil / energy risk premium", note.strip()[:220], "medium")

    cps = chokepoint_result.get("chokepoints") or []
    if isinstance(cps, list):
        for cp in cps:
            if not isinstance(cp, dict):
                continue
            name = str(cp.get("name") or "")
            risk = cp.get("disruption_risk")
            if "hormuz" in name.lower() and isinstance(risk, (int, float)) and risk >= 35:
                add(
                    f"{name} disruption risk {risk:.0f}/100",
                    "Tanker traffic density, incident reporting, or closure rhetoric in coverage — see chokepoint panel",
                    "high" if risk >= 65 else "medium",
                )
                break

    commodities = energy_result.get("commodities") or []
    if isinstance(commodities, list) and not any("move" in x.get("signal", "").lower() for x in out):
        for c in commodities:
            if not isinstance(c, dict):
                continue
            sym = str(c.get("symbol") or "").upper()
            raw_ch = c.get("change_pct_raw")
            if sym in ("BRENT", "WTI", "CL", "BZ") and isinstance(raw_ch, (int, float)) and abs(raw_ch) >= 1.5:
                add(
                    f"{sym} {raw_ch:+.1f}% (session)",
                    "Geopolitical risk premium — cross-check with Hormuz/Bab el-Mandeb and FININT",
                    "medium",
                )
                break

    fsr = energy_result.get("food_security_risk")
    if isinstance(fsr, (int, float)) and fsr >= 55:
        add(
            f"Food security stress {fsr:.0f}/100",
            "Grain/fertilizer prices and route exposure (incl. chokepoints affecting flows)",
            "low" if fsr < 70 else "medium",
        )

    return out[:5]


def _all_divisions() -> List[DivisionHead]:
    """Instantiate all five divisions."""
    return [
        MilitaryDivision(),
        FinancialDivision(),
        InformationDivision(),
        PoliticalDivision(),
        TechnicalDivision(),
    ]


def _build_full_dag(divisions: List[DivisionHead]) -> Tuple[List[DAGNode], Dict[str, Any]]:
    """Build the complete DAG from all divisions plus the CEO synthesis node.

    Returns (nodes, executors).
    """
    all_nodes: List[DAGNode] = []
    all_executors: Dict[str, Any] = {}

    # ACLED reference node (independent Tier 1)
    all_nodes.append(
        DAGNode(
            id="acled_refs",
            node_type="agent",
            streamable=True,
            timeout_s=75.0,
        )
    )

    # Compliance build node (Tier 3)
    all_nodes.append(
        DAGNode(
            id="compliance_build",
            dependencies=["sigint", "diplo"],
            optional_deps=["mil_sigint_chokepoint_enrich"],
            node_type="enrichment",
            timeout_s=15.0,
        )
    )

    for div in divisions:
        div_nodes = div.get_dag_nodes()
        all_nodes.extend(div_nodes)
        all_executors.update(div.get_executors())

    # Context builder: runs after foundation agents; downstream agents use it for collaboration
    all_nodes.append(
        DAGNode(
            id="agent_context",
            dependencies=list(WAVE1_AGENTS),
            node_type="enrichment",
            timeout_s=5.0,
        )
    )
    for node in all_nodes:
        if node.id in WAVE2_AGENTS:
            node.dependencies = list(node.dependencies) + ["agent_context"]

    # Summary node dependencies
    summary_ids = [f"{d.name}_summary" for d in divisions]

    all_nodes.append(
        DAGNode(
            id="ceo_synthesis",
            dependencies=summary_ids + ["compliance_build", "acled_refs"],
            node_type="synthesis",
            streamable=True,
            timeout_s=90.0,
        )
    )

    return all_nodes, all_executors


def _invoke_agent_entry(
    fn: Any,
    conflict: str,
    agent_name: str,
    store: ResultStore,
    *,
    wave2: bool,
) -> Any:
    """Ruft ``run_*_agent`` mit optionalem ``AgentContext`` und ``peers=`` (Snapshot anderer Agenten)."""
    from .analysis_run_state import get_peers_snapshot

    peers = get_peers_snapshot(exclude=agent_name)
    if wave2:
        raw = store.get("agent_context")
        ctx: Any = None
        if raw is not None:
            ctx = AgentContext.model_validate(raw) if isinstance(raw, dict) else raw
        if ctx is not None:
            try:
                return fn(conflict, ctx, peers=peers)
            except TypeError:
                try:
                    return fn(conflict, ctx)
                except TypeError:
                    pass
        try:
            return fn(conflict, peers=peers)
        except TypeError:
            return fn(conflict)
    try:
        return fn(conflict, peers=peers)
    except TypeError:
        return fn(conflict)


def _build_agent_executors(conflict: str, registry: AgentRegistry) -> Dict[str, Any]:
    """Build executor callables for all Tier 1 agent nodes; jeder Agent erhält optional ``peers``."""
    executors: Dict[str, Any] = {}
    for desc in registry.all_agents():
        entry_func = registry.get_entry_func(desc.name)
        if entry_func is None:
            continue
        agent_name = desc.name
        fn = entry_func
        wave2 = agent_name in WAVE2_AGENTS

        def _make_executor(_fn: Any = fn, _c: str = conflict, _name: str = agent_name, _w2: bool = wave2):
            def executor(store: ResultStore) -> Any:
                return _invoke_agent_entry(_fn, _c, _name, store, wave2=_w2)

            return executor

        executors[agent_name] = _make_executor()
    return executors


def _build_infrastructure_executors(conflict: str) -> Dict[str, Any]:
    """Build executors for ACLED refs and compliance."""
    executors = {}

    def exec_acled(store):
        try:
            from .acled_reference import fetch_acled_reference_analyses_sync

            refs = fetch_acled_reference_analyses_sync(conflict)
            return refs if isinstance(refs, list) else []
        except Exception as e:
            logger.warning("ACLED reference fetch failed: %s", e)
            return []

    def exec_agent_context(store):
        """Build shared context from foundation agents for WAVE2 (context-aware) agents."""
        try:
            wave1_raw = {k: store.get(k) for k in WAVE1_AGENTS}
            wave1_dict = {k: _as_dict(v) for k, v in wave1_raw.items()}
            ctx = build_context_from_results(wave1_dict)
            return ctx.model_dump(mode="json")
        except Exception as e:
            logger.warning("Agent context build failed: %s", e)
            return AgentContext().model_dump(mode="json")

    def exec_compliance(store):
        try:
            from .compliance_enrichment import build_compliance_and_alerts

            sigint_data = _as_dict(store.get("sigint"))
            diplo_data = _as_dict(store.get("diplo"))
            state_store = get_agent_state_store()
            prev_entry = state_store.get_result(conflict, "sigint")
            prev_sigint = prev_entry[0] if prev_entry else None
            prev_ts = prev_entry[1] if prev_entry else None
            if prev_sigint and hasattr(prev_sigint, "data"):
                prev_sigint = prev_sigint.data if isinstance(prev_sigint.data, dict) else {}

            all_results = store.all_results()
            agent_results = {
                k: _as_dict(v) for k, v in all_results.items() if not k.endswith("_summary") and k != "ceo_synthesis"
            }

            threat_level = "ELEVATED"
            compliance, alerts, upd_prev, upd_ts = build_compliance_and_alerts(
                sigint_data,
                conflict,
                threat_level,
                diplo_data,
                agent_results,
                prev_sigint,
                prev_ts,
            )
            return {"compliance": compliance, "alerts": alerts}
        except Exception as e:
            logger.warning("Compliance build failed: %s", e)
            return {"compliance": {}, "alerts": []}

    executors["acled_refs"] = exec_acled
    executors["agent_context"] = exec_agent_context
    executors["compliance_build"] = exec_compliance
    return executors


def _build_ceo_executor(conflict: str, divisions: List[DivisionHead]) -> Dict[str, Any]:
    """Build the CEO synthesis executor."""

    def exec_ceo(store):
        return _ceo_synthesize(conflict, divisions, store)

    return {"ceo_synthesis": exec_ceo}


def _ceo_synthesize(conflict: str, divisions: List[DivisionHead], store: ResultStore) -> Dict[str, Any]:
    """CEO-level synthesis: weighted score, LLM or rule-based, full response."""
    # Collect division results
    division_results: Dict[str, DivisionResult] = {}
    for div in divisions:
        dr = store.get(f"{div.name}_summary")
        if isinstance(dr, DivisionResult):
            division_results[div.name] = dr

    # Division composite score (kept as diagnostic context).
    total_weight = sum(CEO_WEIGHTS.get(d, 0) for d in division_results)
    if total_weight > 0:
        division_composite = sum(
            dr.score * (CEO_WEIGHTS.get(name, 0) / total_weight) for name, dr in division_results.items()
        )
    else:
        division_composite = 0.0

    agent_results = {
        name: _as_dict(store.get(name))
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

    agent_data_confidence: Dict[str, str] = {
        name: infer_data_confidence_from_result(agent_results.get(name)) for name in CEO_LEGACY_AGENT_WEIGHTS
    }
    degraded_agents = sorted([n for n, c in agent_data_confidence.items() if c == "degraded"])

    finint_score = _coerce_float(finint_result.get("escalation_score"), 0.0)
    sigint_score = _coerce_float(sigint_result.get("sigint_score"), 0.0)
    news_score = _coerce_float(news_result.get("news_score"), 0.0)
    geoint_score = _coerce_float(geoint_result.get("geoint_score"), 0.0)
    satintel_score = _coerce_float(satintel_result.get("satintel_score"), 0.0)
    socmint_score = _coerce_float(socmint_result.get("socmint_score"), 0.0)
    techint_score = _coerce_float(techint_result.get("techint_score"), 0.0)
    cyber_score = _coerce_float(cyber_result.get("cyber_score"), 0.0)
    energy_score = _coerce_float(energy_result.get("energy_score"), 0.0)
    protest_score = _coerce_float(protest_result.get("protest_score"), 0.0)
    diplo_score = _coerce_float(diplo_result.get("diplo_score"), 0.0)
    proximity_score = _coerce_float(proximity_result.get("proximity_score"), 0.0)
    chokepoint_score = _coerce_float(chokepoint_result.get("chokepoint_score"), 0.0)

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
    }
    legacy_combined, legacy_active_weight = _legacy_combined_excluding_degraded(scores_by_agent, agent_data_confidence)
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
        )
    )
    has_legacy_signal = has_agent_scores and legacy_active_weight > 0
    synthesis_score = legacy_combined if has_legacy_signal else division_composite

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
    }

    temporal_context: Dict[str, Any] = {}
    try:
        from services.agent_score_history import get_temporal_context

        temporal_context = get_temporal_context(conflict, agent_scores_for_predictive)
    except Exception:
        pass

    if synthesis_score >= 80:
        threat_level = "CRITICAL"
    elif synthesis_score >= 60:
        threat_level = "HIGH"
    elif synthesis_score >= 40:
        threat_level = "ELEVATED"
    elif synthesis_score >= 20:
        threat_level = "LOW"
    else:
        threat_level = "MINIMAL"

    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    key_findings = []
    key_findings_context = []
    key_findings_confidence: List[str] = []
    root_cause_suggestions: List[Dict[str, str]] = []
    scenarios = []
    summary = _build_rule_based_ceo_summary(
        conflict, synthesis_score, threat_level, division_results, degraded_agents=degraded_agents
    )

    supervisor_payload = _build_supervisor_user_payload(
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
        temporal_context,
    )

    if use_rule_based:
        for name, dr in sorted(division_results.items(), key=lambda x: -x[1].score):
            if dr.anomalies:
                for a in dr.anomalies:
                    key_findings.append(f"[{name}] {a.description}")
                    key_findings_confidence.append("medium")
        synthesis_meta = {"mode": "rule_based", "reason": "disabled_by_env"}
    else:
        synthesis_meta = {"mode": "rule_based", "reason": "llm_not_attempted"}
        try:
            from .llm import call_llm, get_model_name, require_api_key
            from .utils import parse_llm_json

            require_api_key()
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
            ]

            use_fallback = os.getenv("USE_SUPERVISOR_FALLBACK_MODEL", "false").strip().lower() in ("1", "true", "yes")
            complex_case = use_fallback and _agents_seem_contradictory(agent_scores_list)

            user_payload = supervisor_payload
            user_json = json.dumps(user_payload, default=str)
            if len(user_json) > _MAX_PAYLOAD_CHARS:
                user_json = user_json[:_MAX_PAYLOAD_CHARS]

            tried_models: List[str] = []
            parse_error: str | None = None
            model_candidates = []
            if complex_case:
                model_candidates.append(get_model_name("supervisor_fallback"))
                model_candidates.append(get_model_name("supervisor_routine"))
            else:
                model_candidates.append(get_model_name("supervisor_routine"))
                model_candidates.append(get_model_name("supervisor_fallback"))

            for model in model_candidates:
                if not model or model in tried_models:
                    continue
                tried_models.append(model)
                raw = None
                llm_error: Exception | None = None
                for _ in range(3):
                    try:
                        raw = call_llm(
                            system=_CEO_SYSTEM_PROMPT,
                            user_content=user_json,
                            model=model,
                            temperature=0.1,
                        )
                        llm_error = None
                        break
                    except Exception as e:  # pragma: no cover - retry path is integration/runtime dependent
                        llm_error = e
                if llm_error is not None:
                    parse_error = f"llm_error:{type(llm_error).__name__}:{model}"
                    continue
                parsed = parse_llm_json(raw) if raw else None
                if not isinstance(parsed, dict):
                    parse_error = f"invalid_json_from_model:{model}"
                    continue

                key_findings = list(parsed.get("key_findings") or [])
                key_findings_context = list(parsed.get("key_findings_context") or [])
                raw_conf = parsed.get("key_findings_confidence")
                if isinstance(raw_conf, list):
                    key_findings_confidence = [_normalize_finding_confidence(x) for x in raw_conf]
                else:
                    key_findings_confidence = []
                root_cause_suggestions = _normalize_root_cause_suggestions(parsed.get("root_cause_suggestions"))
                scenarios = list(parsed.get("scenarios") or [])
                summary = str(parsed.get("summary", summary))
                if parsed.get("threat_level"):
                    threat_level = str(parsed["threat_level"])
                synthesis_meta = {"mode": "llm", "model": model, "tried_models": tried_models}
                break
            else:
                synthesis_meta = {
                    "mode": "rule_based",
                    "reason": parse_error or "empty_llm_response",
                    "tried_models": tried_models,
                }
        except Exception as e:
            synthesis_meta = {"mode": "rule_based", "reason": f"llm_error:{type(e).__name__}"}
            logger.warning("CEO LLM synthesis failed: %s — using rule-based fallback", e)

    key_findings_confidence = _align_key_findings_confidence(key_findings, key_findings_confidence)

    # Append agent findings
    try:
        from .findings_builder import append_agent_findings

        all_agent_results = {k: _as_dict(v) for k, v in store.all_results().items()}
        key_findings = append_agent_findings(
            key_findings,
            all_agent_results,
            conflict,
            chokepoint_score,
            key_findings_confidence,
        )
    except Exception:
        pass

    key_findings_confidence = _align_key_findings_confidence(key_findings, key_findings_confidence)

    if len(key_findings_context) > len(key_findings):
        key_findings_context = key_findings_context[: len(key_findings)]

    if not root_cause_suggestions:
        root_cause_suggestions = _heuristic_root_causes(energy_result, chokepoint_result)

    # Actors
    try:
        from .actor_model import build_actors_for_conflict

        actors = build_actors_for_conflict(conflict, key_findings)
    except Exception:
        actors = []

    # Predictive
    try:
        from .predictive import build_predictive_block

        predictive = build_predictive_block(
            conflict, synthesis_score, agent_scores_for_predictive, degraded_agents=degraded_agents
        )
    except Exception:
        predictive = {}

    # Compliance + Alerts
    comp_result = store.get("compliance_build") or {}
    compliance = comp_result.get("compliance", {}) if isinstance(comp_result, dict) else {}
    alerts = comp_result.get("alerts", []) if isinstance(comp_result, dict) else []

    try:
        from .narrative_synthesis import synthesize_narrative

        narrative_story = synthesize_narrative(supervisor_payload)
    except Exception:
        narrative_story = ""

    # Build backwards-compatible response
    response = {
        "conflict": conflict,
        "escalation_score": round(synthesis_score, 1),
        "threat_level": threat_level,
        "key_findings": key_findings,
        "key_findings_context": key_findings_context,
        "key_findings_confidence": key_findings_confidence,
        "corroborated_patterns": [],
        "scenarios": scenarios,
        "summary": summary,
        "narrative_story": narrative_story,
        "actors": actors,
        "predictive": predictive,
        "compliance": compliance,
        "alerts": alerts,
        "pattern_flags": [],
        "synthesis_meta": synthesis_meta,
        "agent_data_confidence": agent_data_confidence,
        "degraded_agents": degraded_agents,
        "temporal_context": temporal_context,
    }

    # Include per-agent raw results for API compatibility
    for agent_name in [
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
    ]:
        raw_result = store.get(agent_name)
        response[agent_name] = _as_dict(raw_result) if raw_result else {}

    # Division metadata (new)
    response["divisions"] = {name: dr.model_dump(mode="json") for name, dr in division_results.items()}

    try:
        from services.agent_score_history import record_daily_scores

        record_daily_scores(conflict, agent_scores_for_predictive)
    except Exception:
        pass

    return response


def _build_rule_based_ceo_summary(
    conflict: str,
    composite: float,
    threat_level: str,
    division_results: Dict[str, DivisionResult],
    *,
    degraded_agents: Optional[List[str]] = None,
) -> str:
    """
    Build a deterministic 2-3 sentence CEO recap when LLM synthesis is unavailable.
    """
    degraded_agents = degraded_agents or []
    ordered = sorted(division_results.items(), key=lambda x: -x[1].score)
    top_name, top_result = ordered[0] if ordered else ("overall", None)
    second_name, second_result = ordered[1] if len(ordered) > 1 else (None, None)

    sentence_1 = (
        f"{conflict}: overall escalation is {composite:.0f}/100 ({threat_level}), "
        f"driven primarily by {top_name} signals."
    )

    sentence_2 = ""
    if second_name and second_result is not None:
        sentence_2 = (
            f"Secondary pressure comes from {second_name} indicators "
            f"(score {second_result.score:.0f}) while {top_name} remains elevated "
            f"(score {top_result.score:.0f})."
        )
    elif top_result is not None:
        sentence_2 = f"{top_name.title()} indicators are currently the dominant risk driver."

    anomaly_notes: List[str] = []
    for name, dr in ordered:
        if not dr.anomalies:
            continue
        # Keep only the first anomaly per division to avoid noisy recaps.
        first = dr.anomalies[0]
        anomaly_notes.append(f"{name}: {first.description}")
        if len(anomaly_notes) >= 2:
            break

    if anomaly_notes:
        sentence_3 = f"Watch items: {'; '.join(anomaly_notes)}."
        body = f"{sentence_1} {sentence_2} {sentence_3}".strip()
    else:
        body = f"{sentence_1} {sentence_2}".strip()

    if degraded_agents:
        return f"{_degraded_streams_caveat(degraded_agents)}\n\n{body}".strip()
    return body


def _agents_seem_contradictory(scores: List[float]) -> bool:
    if len(scores) < 2:
        return False
    threshold = float(os.getenv("SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD", "50"))
    return (max(scores) - min(scores)) >= threshold


def _compact_for_llm(agent_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Compact agent result payload for supervisor-style synthesis prompt."""
    if agent_name == "narrative":
        return {
            "synthesis_text": (result.get("synthesis_text") or "")[:800],
            "synthesis_probability": result.get("synthesis_probability", 0.0),
            "signal_assessment": result.get("signal_assessment") or {},
            "source_comparison_table": (result.get("source_comparison_table") or [])[:3],
            "anomalies": (result.get("anomalies") or [])[:5],
            "state_item_count": result.get("state_item_count", 0),
            "exile_item_count": result.get("exile_item_count", 0),
        }
    score_keys = [k for k in result if k.endswith("_score") or k == "escalation_score"]
    out: Dict[str, Any] = {k: result[k] for k in score_keys if k in result}
    if "summary" in result:
        s = result["summary"]
        out["summary"] = s[:600] if isinstance(s, str) else str(s)[:600]
    for key in (
        "articles",
        "top_signals",
        "conflict_reports",
        "threat_reports",
        "protest_articles",
        "un_icj_news",
        "evidence",
        "hotspots",
        "tech_indicators",
        "export_controls",
        "ioda_events",
        "protest_events",
        "commodities",
        "otx_pulses",
        "imagery_signals",
    ):
        items = result.get(key)
        if isinstance(items, list) and items:
            compact = []
            for item in items[:3]:
                if isinstance(item, dict):
                    compact.append(
                        {
                            k: (str(v)[:120] if isinstance(v, str) and len(v) > 120 else v)
                            for k, v in list(item.items())[:6]
                        }
                    )
                elif isinstance(item, str):
                    compact.append(item[:150])
                else:
                    compact.append(item)
            out[key] = compact
    for key in ("aircraft", "ships"):
        items = result.get(key)
        if isinstance(items, list):
            out[f"{key}_count"] = len([i for i in items if isinstance(i, dict) and "error" not in i])
    for key in (
        "brent",
        "polymarket",
        "cisa_kev",
        "ofac_sdn",
        "eu_sanctions",
        "agsi_storage",
        "greynoise_scan_context",
        "food_commodities",
        "fao_fpi",
        "fertilizer",
        "food_security_risk",
    ):
        val = result.get(key)
        if val is not None:
            s = json.dumps(val, default=str)
            if len(s) < 500:
                out[key] = val
    if agent_name == "chokepoint":
        out["chokepoints"] = (result.get("chokepoints") or [])[:5]
        out["chokepoint_score"] = result.get("chokepoint_score", 0.0)
        dc = result.get("data_confidence")
        if dc in ("live", "estimated", "degraded"):
            out["data_confidence"] = dc
    return out


def _build_supervisor_user_payload(
    conflict: str,
    synthesis_score: float,
    threat_level: str,
    division_composite: float,
    division_results: Dict[str, DivisionResult],
    acled_refs: Any,
    agent_data_confidence: Dict[str, str],
    degraded_agents: List[str],
    finint_result: Dict[str, Any],
    sigint_result: Dict[str, Any],
    news_result: Dict[str, Any],
    geoint_result: Dict[str, Any],
    satintel_result: Dict[str, Any],
    socmint_result: Dict[str, Any],
    techint_result: Dict[str, Any],
    cyber_result: Dict[str, Any],
    energy_result: Dict[str, Any],
    protest_result: Dict[str, Any],
    diplo_result: Dict[str, Any],
    proximity_result: Dict[str, Any],
    narrative_result: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
    temporal_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Shared compact payload for CEO LLM supervisor and cross-stream narrative synthesis."""
    finint_score = _coerce_float(finint_result.get("escalation_score"), 0.0)
    sigint_score = _coerce_float(sigint_result.get("sigint_score"), 0.0)
    news_score = _coerce_float(news_result.get("news_score"), 0.0)
    geoint_score = _coerce_float(geoint_result.get("geoint_score"), 0.0)
    satintel_score = _coerce_float(satintel_result.get("satintel_score"), 0.0)
    socmint_score = _coerce_float(socmint_result.get("socmint_score"), 0.0)
    techint_score = _coerce_float(techint_result.get("techint_score"), 0.0)
    cyber_score = _coerce_float(cyber_result.get("cyber_score"), 0.0)
    energy_score = _coerce_float(energy_result.get("energy_score"), 0.0)
    protest_score = _coerce_float(protest_result.get("protest_score"), 0.0)
    diplo_score = _coerce_float(diplo_result.get("diplo_score"), 0.0)
    proximity_score = _coerce_float(proximity_result.get("proximity_score"), 0.0)
    chokepoint_score = _coerce_float(chokepoint_result.get("chokepoint_score"), 0.0)

    return {
        "conflict": conflict,
        "composite_score": synthesis_score,
        "threat_level": threat_level,
        "division_composite_score": division_composite,
        "division_scores": {name: dr.score for name, dr in division_results.items()},
        "acled_reference_analyses": [
            {"url": r.get("url"), "title": r.get("title"), "excerpt": (r.get("excerpt") or "")[:1000]}
            for r in (acled_refs or [])[:3]
            if isinstance(r, dict) and (r.get("excerpt") or r.get("title"))
        ],
        "agent_data_confidence": agent_data_confidence,
        "degraded_agents": degraded_agents,
        "agent_scores": {
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
        },
        "finint": _compact_for_llm("finint", finint_result),
        "sigint": _compact_for_llm("sigint", sigint_result),
        "news": _compact_for_llm("news", news_result),
        "geoint": _compact_for_llm("geoint", geoint_result),
        "satintel": _compact_for_llm("satintel", satintel_result),
        "socmint": _compact_for_llm("socmint", socmint_result),
        "techint": _compact_for_llm("techint", techint_result),
        "cyber": _compact_for_llm("cyber", cyber_result),
        "energy": _compact_for_llm("energy", energy_result),
        "protest": _compact_for_llm("protest", protest_result),
        "diplo": _compact_for_llm("diplo", diplo_result),
        "proximity": _compact_for_llm("proximity", proximity_result),
        "narrative": _compact_for_llm("narrative", narrative_result),
        "chokepoint": _compact_for_llm("chokepoint", chokepoint_result),
        "agent_score_temporal": temporal_context or {},
    }


def _build_ceo_prompt(
    conflict: str, division_results: Dict[str, DivisionResult], composite: float, store: ResultStore
) -> str:
    """Build the delta-aware CEO prompt."""
    parts = [
        f"CONFLICT: {conflict}",
        f"COMPOSITE SCORE: {composite:.1f}",
        "",
        "DIVISIONS (by score, highest first):",
    ]

    sorted_divs = sorted(division_results.items(), key=lambda x: -x[1].score)
    for i, (name, dr) in enumerate(sorted_divs, 1):
        anomaly_note = f" [{len(dr.anomalies)} anomalies]" if dr.anomalies else ""
        parts.append(f"  {i}. {name.title()}: Score {dr.score:.0f}{anomaly_note}")
        parts.append(f"     {dr.summary[:300]}")
        if dr.anomalies:
            for a in dr.anomalies:
                parts.append(f"     ! [{a.severity}] {a.description}")

    # Entity summary
    ner_reg = store.get("ner_extract")
    if isinstance(ner_reg, EntityRegistry):
        entity_count = ner_reg.count
        parts.append(f"\nENTITIES: {entity_count} total")
        for etype in ["PERSON", "ORG", "LOCATION", "VESSEL"]:
            ents = ner_reg.get_by_type(etype)
            if ents:
                names = [e.entity for e in ents[:5]]
                parts.append(f"  {etype}: {', '.join(names)}")

    parts.append("\nTASK: Produce a holistic assessment. Focus on cross-division patterns and changes.")
    parts.append(
        'OUTPUT: JSON: { "escalation_score": ..., "threat_level": ..., "key_findings": [...], '
        '"key_findings_context": [...], "key_findings_confidence": [...], '
        '"root_cause_suggestions": [...], "scenarios": [...], "summary": "..." }'
    )

    return "\n".join(parts)


_CEO_SYSTEM_PROMPT = """You are a senior intelligence analyst with access to 10 intelligence streams:
- FININT: Financial markets and oil price indicators
- SIGINT: Military aircraft, naval vessels, and conflict intel (BBC, DW, Al Jazeera, RFE/RL, think tanks)
- NEWS: Open-source media sentiment analysis
- GEOINT: Satellite thermal anomaly detection
- SATINTEL: Sentinel Hub/Copernicus satellite imagery signal scoring
- SOCMINT: Social media signals from Telegram, Reddit, and RSS
- TECHINT: Tech sector indicators, export control news, IODA internet outage events (escalation signal)
- CYBER: CISA KEV, threat intel reports, OTX pulses (APT/exploit indicators)
- ENERGY: EU gas storage (AGSI+), commodity prices (Brent, WTI), food commodities (Wheat, Corn, Soy), FAO Food Price Index, fertilizer prices (Urea, DAP), food security risk
- PROTEST: ACLED protests/riots, GDELT protest coverage (civil society unrest)
- DIPLO: OFAC/EU sanctions, UN/ICJ press (diplomatic/legal signals)
- PROXIMITY: Strike-civilian correlation (NASA FIRMS + OSM schools/hospitals, human-shield / collateral risk)
- CHOKEPOINT: Maritime chokepoint monitoring (Strait of Hormuz, Bab el-Mandeb, Suez Canal) - tanker density, oil flow estimates, disruption risk scoring, data quality transparency

DATA CONFIDENCE (required): The payload includes "agent_data_confidence" per stream: "live" (primary sensors/APIs), "estimated" (proxies or partial feeds), "degraded" (no reliable feed). The list "degraded_agents" names streams whose numeric scores must NOT be read as evidence of safety — low scores there usually mean missing data, not a calm situation. When "degraded_agents" is non-empty, you MUST state explicitly which streams are degraded and warn that the composite may understate risk. Do not imply the theater is quiet based solely on low scores from degraded streams.

When the payload includes "narrative", this is the Signal Framework: state vs exile/independent media comparison. Use synthesis_text, synthesis_probability, and source_comparison_table to inform key_findings and summary when relevant.

When the payload includes "acled_reference_analyses", these are curated ACLED analysis pages whose content has been fetched and extracted. Use these analyses to inform key_findings, scenarios, and summary as substantive context.

When the payload includes "agent_score_temporal", it holds per-agent temporal context: delta_vs_prior_utc_day (vs last stored UTC day), trend_7d (rising|falling|stable|insufficient_data), consecutive_days_up/down, and daily_scores_7d. Prefer trend and momentum over one-off scores when framing findings (e.g. stable baseline vs multi-day climb).

Analyze all streams holistically and return ONLY valid JSON with no markdown:
{
  "escalation_score": <number 0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise finding strings>],
  "key_findings_context": [<optional: array of 2-3 sentence "why this matters" per finding, same order as key_findings>],
  "key_findings_confidence": [<required: same length as key_findings; each value "high", "medium", or "low" — assessment confidence in that finding>],
  "root_cause_suggestions": [<up to 5 objects: plausible links between an observable signal and a driver, e.g. {"signal": "Brent +3%", "likely_cause": "Strait of Hormuz risk premium from tanker/incident coverage", "confidence": "medium"} — hypotheses not facts>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF summary>"
}"""


# ---------------------------------------------------------------------------
# Public API: analyze_conflict via DAG
# ---------------------------------------------------------------------------


def analyze_conflict_dag(conflict: str) -> Dict[str, Any]:
    """Run the full multi-agent hierarchy analysis using the DAG scheduler.

    Returns the same response format as the original supervisor.analyze_conflict().
    """
    try:
        from services.source_fetch import clear_run_cache

        clear_run_cache()
    except ImportError:
        pass

    registry = get_agent_registry()
    divisions = _all_divisions()

    # Build DAG
    dag_nodes, division_executors = _build_full_dag(divisions)
    agent_executors = _build_agent_executors(conflict, registry)
    infra_executors = _build_infrastructure_executors(conflict)
    ceo_executors = _build_ceo_executor(conflict, divisions)

    all_executors = {
        **agent_executors,
        **division_executors,
        **infra_executors,
        **ceo_executors,
    }

    # Create store and run
    store_mgr = ResultStoreManager()
    cycle_id = f"{conflict}_{int(time.time())}"
    store = store_mgr.create_store(conflict, cycle_id)

    scheduler = DAGScheduler(dag_nodes)
    scheduler.run(all_executors, store)

    # Extract CEO result
    ceo_result = store.get("ceo_synthesis")
    if isinstance(ceo_result, dict):
        return ceo_result

    # If the DAG node timed out or returned a non-dict fallback, try one direct
    # deterministic synthesis pass from collected store data before failing hard.
    try:
        recovered = _ceo_synthesize(conflict, divisions, store)
        if isinstance(recovered, dict):
            return recovered
    except Exception as exc:
        logger.warning("CEO synthesis recovery failed: %s", exc)

    return {
        "conflict": conflict,
        "escalation_score": 0,
        "threat_level": "MINIMAL",
        "key_findings": [],
        "key_findings_confidence": [],
        "root_cause_suggestions": [],
        "scenarios": [],
        "summary": "Analysis failed.",
    }


def analyze_conflict_dag_streaming(conflict: str):
    """Run the full DAG analysis with streaming.

    Yields (node_id, result) for streamable nodes only.
    Final event is ("ceo_synthesis", full_result).
    """
    try:
        from services.source_fetch import clear_run_cache

        clear_run_cache()
    except ImportError:
        pass

    registry = get_agent_registry()
    divisions = _all_divisions()

    dag_nodes, division_executors = _build_full_dag(divisions)
    agent_executors = _build_agent_executors(conflict, registry)
    infra_executors = _build_infrastructure_executors(conflict)
    ceo_executors = _build_ceo_executor(conflict, divisions)

    all_executors = {
        **agent_executors,
        **division_executors,
        **infra_executors,
        **ceo_executors,
    }

    store_mgr = ResultStoreManager()
    cycle_id = f"{conflict}_{int(time.time())}"
    store = store_mgr.create_store(conflict, cycle_id)

    scheduler = DAGScheduler(dag_nodes)
    yield from scheduler.run_streaming(all_executors, store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_dict(result: Any) -> Dict:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data
    return {}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion to keep synthesis resilient to bad agent payloads."""
    try:
        if value is None:
            return default
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            value = stripped
        return float(value)
    except (TypeError, ValueError):
        return default
