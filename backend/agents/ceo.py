"""
CEO Orchestrator – Final DAG-Node (Tier 5: ceo_synthesis).

Reads all 5 Division-Summaries from the ResultStore, computes the weighted
composite score, builds a delta-aware LLM prompt, and produces the final
assessment. Preserves the API response format for backwards compatibility.
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .dag_scheduler import DAGNode, DAGScheduler, ResultStore, ResultStoreManager
from .division import DivisionHead, DivisionResult, CycleLog
from .entity_registry import EntityRegistry
from .registry import AgentRegistry, get_agent_registry
from .agent_state_store import AgentStateStore, get_agent_state_store
from .divisions import (
    InformationDivision,
    MilitaryDivision,
    FinancialDivision,
    PoliticalDivision,
    TechnicalDivision,
)

logger = logging.getLogger(__name__)

# CEO-level division weights
CEO_WEIGHTS = {
    "military":    0.30,
    "financial":   0.18,
    "information": 0.22,
    "political":   0.14,
    "technical":   0.16,
}


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
    all_nodes.append(DAGNode(
        id="acled_refs",
        node_type="agent",
        streamable=True,
        timeout_s=75.0,
    ))

    # Compliance build node (Tier 3)
    all_nodes.append(DAGNode(
        id="compliance_build",
        dependencies=["sigint", "diplo"],
        optional_deps=["mil_sigint_chokepoint_enrich"],
        node_type="enrichment",
        timeout_s=15.0,
    ))

    for div in divisions:
        div_nodes = div.get_dag_nodes()
        all_nodes.extend(div_nodes)
        all_executors.update(div.get_executors())

    # Summary node dependencies
    summary_ids = [f"{d.name}_summary" for d in divisions]

    all_nodes.append(DAGNode(
        id="ceo_synthesis",
        dependencies=summary_ids + ["compliance_build", "acled_refs"],
        node_type="synthesis",
        streamable=True,
        timeout_s=30.0,
    ))

    return all_nodes, all_executors


def _build_agent_executors(conflict: str, registry: AgentRegistry) -> Dict[str, Any]:
    """Build executor callables for all Tier 1 agent nodes."""
    executors = {}
    for desc in registry.all_agents():
        entry_func = registry.get_entry_func(desc.name)
        if entry_func is None:
            continue
        agent_name = desc.name
        fn = entry_func
        executors[agent_name] = lambda store, _fn=fn, _c=conflict: _fn(_c)
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
            agent_results = {k: _as_dict(v) for k, v in all_results.items()
                             if not k.endswith("_summary") and k != "ceo_synthesis"}

            threat_level = "ELEVATED"
            compliance, alerts, upd_prev, upd_ts = build_compliance_and_alerts(
                sigint_data, conflict, threat_level, diplo_data,
                agent_results, prev_sigint, prev_ts,
            )
            return {"compliance": compliance, "alerts": alerts}
        except Exception as e:
            logger.warning("Compliance build failed: %s", e)
            return {"compliance": {}, "alerts": []}

    executors["acled_refs"] = exec_acled
    executors["compliance_build"] = exec_compliance
    return executors


def _build_ceo_executor(conflict: str, divisions: List[DivisionHead]) -> Dict[str, Any]:
    """Build the CEO synthesis executor."""

    def exec_ceo(store):
        return _ceo_synthesize(conflict, divisions, store)

    return {"ceo_synthesis": exec_ceo}


def _ceo_synthesize(conflict: str, divisions: List[DivisionHead],
                    store: ResultStore) -> Dict[str, Any]:
    """CEO-level synthesis: weighted score, LLM or rule-based, full response."""
    # Collect division results
    division_results: Dict[str, DivisionResult] = {}
    for div in divisions:
        dr = store.get(f"{div.name}_summary")
        if isinstance(dr, DivisionResult):
            division_results[div.name] = dr

    # Composite score
    total_weight = sum(CEO_WEIGHTS.get(d, 0) for d in division_results)
    if total_weight > 0:
        composite = sum(
            dr.score * (CEO_WEIGHTS.get(name, 0) / total_weight)
            for name, dr in division_results.items()
        )
    else:
        composite = 0.0

    # Per-agent scores for backwards compatibility
    agent_scores = {}
    for dr in division_results.values():
        agent_scores.update(dr.agent_scores)

    # Score-to-threat-level
    if composite >= 80: threat_level = "CRITICAL"
    elif composite >= 60: threat_level = "HIGH"
    elif composite >= 40: threat_level = "ELEVATED"
    elif composite >= 20: threat_level = "LOW"
    else: threat_level = "MINIMAL"

    # Rule-based or LLM synthesis
    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    key_findings = []
    key_findings_context = []
    scenarios = []
    summary = f"Composite {composite:.0f}/100."

    if use_rule_based:
        for name, dr in sorted(division_results.items(), key=lambda x: -x[1].score):
            if dr.anomalies:
                for a in dr.anomalies:
                    key_findings.append(f"[{name}] {a.description}")
    else:
        try:
            from .llm import call_llm, get_model_name, require_api_key
            require_api_key()
            prompt = _build_ceo_prompt(conflict, division_results, composite, store)
            model = get_model_name("supervisor_routine")
            raw = call_llm(
                system=_CEO_SYSTEM_PROMPT,
                user_content=prompt,
                model=model,
                temperature=0.1,
            )
            if raw:
                raw = raw.strip()
                if "```" in raw:
                    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                    if m:
                        raw = m.group(1).strip()
                parsed = json.loads(raw)
                key_findings = list(parsed.get("key_findings") or [])
                key_findings_context = list(parsed.get("key_findings_context") or [])
                scenarios = list(parsed.get("scenarios") or [])
                summary = str(parsed.get("summary", summary))
                if parsed.get("threat_level"):
                    threat_level = parsed["threat_level"]
        except Exception as e:
            logger.warning("CEO LLM synthesis failed: %s — using rule-based fallback", e)

    # Append agent findings
    try:
        from .findings_builder import append_agent_findings
        all_agent_results = {k: _as_dict(v) for k, v in store.all_results().items()}
        chokepoint_score = agent_scores.get("chokepoint", 0)
        key_findings = append_agent_findings(key_findings, all_agent_results, conflict, chokepoint_score)
    except Exception:
        pass

    # Actors
    try:
        from .actor_model import build_actors_for_conflict
        actors = build_actors_for_conflict(conflict, key_findings)
    except Exception:
        actors = []

    # Predictive
    try:
        from .predictive import build_predictive_block
        predictive = build_predictive_block(conflict, composite, agent_scores)
    except Exception:
        predictive = {}

    # Compliance + Alerts
    comp_result = store.get("compliance_build") or {}
    compliance = comp_result.get("compliance", {}) if isinstance(comp_result, dict) else {}
    alerts = comp_result.get("alerts", []) if isinstance(comp_result, dict) else []

    # Build backwards-compatible response
    response = {
        "conflict": conflict,
        "escalation_score": round(composite, 1),
        "threat_level": threat_level,
        "key_findings": key_findings,
        "key_findings_context": key_findings_context,
        "corroborated_patterns": [],
        "scenarios": scenarios,
        "summary": summary,
        "actors": actors,
        "predictive": predictive,
        "compliance": compliance,
        "alerts": alerts,
    }

    # Include per-agent raw results for API compatibility
    for agent_name in ["finint", "sigint", "news", "geoint", "socmint",
                        "techint", "cyber", "energy", "protest", "diplo",
                        "proximity", "narrative", "chokepoint"]:
        raw_result = store.get(agent_name)
        response[agent_name] = _as_dict(raw_result) if raw_result else {}

    # Division metadata (new)
    response["divisions"] = {
        name: dr.model_dump(mode="json")
        for name, dr in division_results.items()
    }

    return response


def _build_ceo_prompt(conflict: str, division_results: Dict[str, DivisionResult],
                      composite: float, store: ResultStore) -> str:
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
    parts.append('OUTPUT: JSON: { "escalation_score": ..., "threat_level": ..., "key_findings": [...], '
                 '"key_findings_context": [...], "scenarios": [...], "summary": "..." }')

    return "\n".join(parts)


_CEO_SYSTEM_PROMPT = """You are the Chief Intelligence Officer (CEO) for a geopolitical monitoring system.
You receive structured summaries from 5 intelligence divisions: Military, Financial, Information, Political, Technical.
Each division has already analyzed and scored their domain. Your task is to synthesize across domains.

Focus on:
- Cross-domain correlations (e.g., military buildup + energy price spike + media escalation)
- Anomalies flagged by divisions
- Changes since last cycle (deltas)
- Concrete, actionable findings

Return ONLY valid JSON:
{
  "escalation_score": <0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise findings>],
  "key_findings_context": [<array of 2-3 sentence context per finding>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF>"
}"""


# ---------------------------------------------------------------------------
# Public API: analyze_conflict via DAG
# ---------------------------------------------------------------------------

def analyze_conflict_dag(conflict: str) -> Dict[str, Any]:
    """Run the full multi-agent hierarchy analysis using the DAG scheduler.

    Returns the same response format as the original supervisor.analyze_conflict().
    """
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

    return {"conflict": conflict, "escalation_score": 0, "threat_level": "MINIMAL",
            "key_findings": [], "scenarios": [], "summary": "Analysis failed."}


def analyze_conflict_dag_streaming(conflict: str):
    """Run the full DAG analysis with streaming.

    Yields (node_id, result) for streamable nodes only.
    Final event is ("ceo_synthesis", full_result).
    """
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
