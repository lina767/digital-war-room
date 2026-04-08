"""DAG construction, executors, and analyze_conflict_dag entrypoints."""

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Tuple

from .config import DISABLED_AGENTS
from .agent_state_store import get_agent_state_store
from .ceo_synthesize import _ceo_synthesize
from .ceo_util import as_dict
from .context import WAVE1_AGENTS, WAVE2_AGENTS, AgentContext, build_context_from_results
from .dag_scheduler import DAGNode, DAGScheduler, ResultStore, ResultStoreManager
from .division import DivisionHead
from .divisions import (
    FinancialDivision,
    InformationDivision,
    MilitaryDivision,
    PoliticalDivision,
    TechnicalDivision,
)
from .registry import AgentRegistry, get_agent_registry
from .utils import get_analysis_run_id, reset_analysis_run_id, set_analysis_run_id

logger = logging.getLogger(__name__)


def _disabled_dag_nodes() -> set[str]:
    raw = os.getenv("DISABLED_DAG_NODES", "")
    return {n.strip() for n in raw.split(",") if n.strip()}


def _all_disabled_ids() -> set[str]:
    return set(DISABLED_AGENTS) | _disabled_dag_nodes()


_SCORE_FIELD_BY_AGENT: Dict[str, str] = {
    "finint": "escalation_score",
    "sigint": "sigint_score",
    "news": "news_score",
    "geoint": "geoint_score",
    "satintel": "satintel_score",
    "socmint": "socmint_score",
    "techint": "techint_score",
    "cyber": "cyber_score",
    "energy": "energy_score",
    "diplo": "diplo_score",
    "proximity": "proximity_score",
    "narrative": "narrative_score",
    "chokepoint": "chokepoint_score",
    "pentagon": "pentagon_score",
}


def _agent_fallback_payload(agent_id: str) -> Any:
    if agent_id == "acled_refs":
        return []
    if agent_id == "agent_context":
        return AgentContext().model_dump(mode="json")
    score_key = _SCORE_FIELD_BY_AGENT.get(agent_id, f"{agent_id}_score")
    payload: Dict[str, Any] = {
        score_key: 0.0,
        "summary": f"{agent_id} unavailable (timeout/fallback).",
        "_meta": {
            "agent": agent_id,
            "fallback_used": True,
            "data_confidence": "degraded",
            "data_freshness": "unavailable",
            "sources": [],
            "error_summary": "timeout_or_execution_failure",
        },
    }
    if agent_id == "narrative":
        payload.setdefault("synthesis_text", "")
        payload.setdefault("synthesis_probability", 0.0)
    return payload


def _enrichment_fallback_payload(node_id: str) -> Any:
    if node_id == "compliance_build":
        return {"compliance": {}, "alerts": []}
    if node_id == "quality_fusion":
        return {"signals": [], "summary": "", "fusion_meta": {"fallback_used": True}}
    if node_id == "research_enrichment":
        return {"triggered": False, "fallback_used": True}
    if node_id == "comtrade_chokepoint_validate":
        return {"triggered": False, "fallback_used": True}
    if node_id == "agent_context":
        return AgentContext().model_dump(mode="json")
    # Generic safe object for enrichment nodes.
    return {"fallback_used": True}


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

    all_nodes.append(
        DAGNode(
            id="acled_refs",
            node_type="agent",
            streamable=True,
            timeout_s=75.0,
        )
    )

    all_nodes.append(
        DAGNode(
            id="compliance_build",
            dependencies=["sigint", "diplo"],
            optional_deps=["mil_sigint_chokepoint_enrich"],
            node_type="enrichment",
            timeout_s=15.0,
        )
    )

    all_nodes.append(
        DAGNode(
            id="quality_fusion",
            dependencies=["news", "geoint", "socmint", "diplo"],
            node_type="enrichment",
            timeout_s=45.0,
        )
    )
    all_nodes.append(
        DAGNode(
            id="research_enrichment",
            dependencies=[
                "finint",
                "sigint",
                "news",
                "geoint",
                "satintel",
                "socmint",
                "techint",
                "cyber",
                "energy",
                "diplo",
                "proximity",
                "narrative",
                "chokepoint",
                "pentagon",
                "quality_fusion",
            ],
            node_type="enrichment",
            timeout_s=35.0,
        )
    )

    all_nodes.append(
        DAGNode(
            id="comtrade_chokepoint_validate",
            dependencies=["finint", "chokepoint_residual_enrich"],
            node_type="enrichment",
            timeout_s=25.0,
        )
    )

    for div in divisions:
        div_nodes = div.get_dag_nodes()
        all_nodes.extend(div_nodes)
        all_executors.update(div.get_executors())

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
        if node.fallback is None:
            if node.node_type == "agent":
                node.fallback = _agent_fallback_payload(node.id)
            elif node.node_type == "enrichment":
                node.fallback = _enrichment_fallback_payload(node.id)

    summary_ids = [f"{d.name}_summary" for d in divisions]

    all_nodes.append(
        DAGNode(
            id="ceo_synthesis",
            dependencies=summary_ids + ["compliance_build", "acled_refs", "quality_fusion", "research_enrichment"],
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
    disabled_agents = set(DISABLED_AGENTS)
    for desc in registry.all_agents():
        if desc.name in disabled_agents:
            logger.info("Skipping disabled agent executor: %s", desc.name)
            continue
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
    executors: Dict[str, Any] = {}

    def exec_acled(store: ResultStore) -> Any:
        try:
            from .acled_reference import fetch_acled_reference_analyses_sync

            refs = fetch_acled_reference_analyses_sync(conflict)
            return refs if isinstance(refs, list) else []
        except Exception as e:
            logger.warning("ACLED reference fetch failed: %s", e)
            return []

    def exec_agent_context(store: ResultStore) -> Any:
        """Build shared context from foundation agents for WAVE2 (context-aware) agents."""
        try:
            wave1_raw = {k: store.get(k) for k in WAVE1_AGENTS}
            wave1_dict = {k: as_dict(v) for k, v in wave1_raw.items()}
            ctx = build_context_from_results(wave1_dict)
            return ctx.model_dump(mode="json")
        except Exception as e:
            logger.warning("Agent context build failed: %s", e)
            return AgentContext().model_dump(mode="json")

    def exec_compliance(store: ResultStore) -> Dict[str, Any]:
        try:
            from .compliance_enrichment import build_compliance_and_alerts

            sigint_data = as_dict(store.get("sigint"))
            diplo_data = as_dict(store.get("diplo"))
            state_store = get_agent_state_store()
            prev_entry = state_store.get_result(conflict, "sigint")
            prev_sigint = prev_entry[0] if prev_entry else None
            prev_ts = prev_entry[1] if prev_entry else None
            if prev_sigint and hasattr(prev_sigint, "data"):
                prev_sigint = prev_sigint.data if isinstance(prev_sigint.data, dict) else {}

            all_results = store.all_results()
            agent_results = {
                k: as_dict(v) for k, v in all_results.items() if not k.endswith("_summary") and k != "ceo_synthesis"
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

    def exec_quality_fusion(store: ResultStore) -> Dict[str, Any]:
        try:
            from quality.fusion import run_quality_fusion

            agent_results = {
                k: as_dict(store.get(k)) for k in ("news", "geoint", "socmint", "diplo")
            }
            return run_quality_fusion(conflict, agent_results)
        except Exception as e:
            logger.warning("quality_fusion failed: %s", e)
            return {"signals": [], "summary": "", "fusion_meta": {"error": str(e)}}

    def exec_research_enrichment(store: ResultStore) -> Dict[str, Any]:
        try:
            from .research_agent import run_research_enrichment

            agent_results = {
                k: as_dict(store.get(k))
                for k in (
                    "finint",
                    "sigint",
                    "news",
                    "geoint",
                    "satintel",
                    "socmint",
                    "techint",
                    "cyber",
                    "energy",
                    "diplo",
                    "proximity",
                    "narrative",
                    "chokepoint",
                    "pentagon",
                )
            }
            qf = as_dict(store.get("quality_fusion"))
            gate_hint = {"quality_warnings": qf.get("signals") if isinstance(qf.get("signals"), list) else []}
            return run_research_enrichment(
                conflict=conflict,
                agent_results=agent_results,
                data_quality_gate=gate_hint,
            )
        except Exception as e:
            logger.warning("research_enrichment failed: %s", e)
            return {"triggered": False, "error": str(e)}

    def exec_comtrade_chokepoint_validate(store: ResultStore) -> Dict[str, Any]:
        try:
            from .enrichments.comtrade_chokepoint_validate import run_comtrade_chokepoint_validation

            finint_data = as_dict(store.get("finint")) or {}
            # Prefer the post-enriched chokepoint block (includes cross-division signals + overrides).
            chokepoint_data = as_dict(store.get("chokepoint_residual_enrich")) or as_dict(store.get("chokepoint")) or {}
            return run_comtrade_chokepoint_validation(
                conflict=conflict,
                finint_result=finint_data if isinstance(finint_data, dict) else {},
                chokepoint_result=chokepoint_data if isinstance(chokepoint_data, dict) else {},
            )
        except Exception as e:
            logger.warning("comtrade_chokepoint_validate failed: %s", e)
            return {"triggered": False, "error": str(e)}

    executors["acled_refs"] = exec_acled
    executors["agent_context"] = exec_agent_context
    executors["compliance_build"] = exec_compliance
    executors["quality_fusion"] = exec_quality_fusion
    executors["research_enrichment"] = exec_research_enrichment
    executors["comtrade_chokepoint_validate"] = exec_comtrade_chokepoint_validate
    return executors


def _build_ceo_executor(conflict: str, divisions: List[DivisionHead]) -> Dict[str, Any]:
    """Build the CEO synthesis executor."""

    def exec_ceo(store: ResultStore) -> Dict[str, Any]:
        return _ceo_synthesize(conflict, divisions, store)

    return {"ceo_synthesis": exec_ceo}


def analyze_conflict_dag(conflict: str) -> Dict[str, Any]:
    """Run the full multi-agent hierarchy analysis using the DAG scheduler.

    Returns the same response format as the original supervisor.analyze_conflict().
    """
    run_token = set_analysis_run_id(str(uuid.uuid4()))
    try:
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
        disabled_ids = _all_disabled_ids()
        if disabled_ids:
            all_executors = {k: v for k, v in all_executors.items() if k not in disabled_ids}
            logger.info("Disabled DAG executors for this run: %s", sorted(disabled_ids))

        store_mgr = ResultStoreManager()
        cycle_id = f"{conflict}_{int(time.time())}"
        store = store_mgr.create_store(conflict, cycle_id)

        scheduler = DAGScheduler(dag_nodes)
        scheduler.run(all_executors, store)

        ceo_result = store.get("ceo_synthesis")
        if isinstance(ceo_result, dict):
            return ceo_result

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
            "analysis_run_id": get_analysis_run_id(),
            "provenance_index": [],
        }
    finally:
        reset_analysis_run_id(run_token)


def analyze_conflict_dag_streaming(conflict: str):
    """Run the full DAG analysis with streaming.

    Yields (node_id, result) for streamable nodes only.
    Final event is ("ceo_synthesis", full_result).
    """
    run_token = set_analysis_run_id(str(uuid.uuid4()))
    try:
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
        disabled_ids = _all_disabled_ids()
        if disabled_ids:
            all_executors = {k: v for k, v in all_executors.items() if k not in disabled_ids}
            logger.info("Disabled DAG executors for this streaming run: %s", sorted(disabled_ids))

        store_mgr = ResultStoreManager()
        cycle_id = f"{conflict}_{int(time.time())}"
        store = store_mgr.create_store(conflict, cycle_id)

        scheduler = DAGScheduler(dag_nodes)
        yield from scheduler.run_streaming(all_executors, store)
    finally:
        reset_analysis_run_id(run_token)
