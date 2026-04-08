"""Deterministic trigger gate for research enrichment."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from agents.utils import safe_float

from .research_contracts import ResearchTriggerDecision, ResearchTriggerReason

RESEARCH_TRIGGER_ENABLED = (os.getenv("RESEARCH_TRIGGER_ENABLED", "true").strip().lower() in ("1", "true", "yes"))
RESEARCH_TRIGGER_MIN_REASONS = int(os.getenv("RESEARCH_TRIGGER_MIN_REASONS", "1"))
RESEARCH_TRIGGER_SCORE_SPREAD = float(os.getenv("RESEARCH_TRIGGER_SCORE_SPREAD", "45"))
RESEARCH_TRIGGER_DQ_CONFIDENCE_MIN = float(os.getenv("RESEARCH_TRIGGER_DQ_CONFIDENCE_MIN", "40"))
RESEARCH_TRIGGER_PROVENANCE_MIN = float(os.getenv("RESEARCH_TRIGGER_PROVENANCE_MIN", "0.45"))

# field path -> fallback that indicates "missing"
REQUIRED_FIELD_RULES: Dict[str, Any] = {
    "finint.brent": dict,
    "sigint.aircraft": list,
    "news.articles": list,
    "geoint.anomalies": list,
    "diplo.ofac_sdn": dict,
}

SCORE_KEYS: List[Tuple[str, str]] = [
    ("finint", "escalation_score"),
    ("sigint", "sigint_score"),
    ("news", "news_score"),
    ("geoint", "geoint_score"),
    ("satintel", "satintel_score"),
    ("socmint", "socmint_score"),
    ("techint", "techint_score"),
    ("cyber", "cyber_score"),
    ("energy", "energy_score"),
    ("diplo", "diplo_score"),
    ("proximity", "proximity_score"),
    ("chokepoint", "chokepoint_score"),
    ("pentagon", "pentagon_score"),
]


def _is_missing_value(value: Any, expected_type: Any) -> bool:
    if value is None:
        return True
    if expected_type is list:
        return not isinstance(value, list) or len(value) == 0
    if expected_type is dict:
        return not isinstance(value, dict) or len(value) == 0
    if isinstance(value, str):
        return not value.strip()
    return False


def _collect_missing_required_fields(agent_results: Dict[str, Dict[str, Any]]) -> List[str]:
    missing: List[str] = []
    for field_path, expected in REQUIRED_FIELD_RULES.items():
        agent_name, field_name = field_path.split(".", 1)
        block = agent_results.get(agent_name) or {}
        if not isinstance(block, dict):
            missing.append(field_path)
            continue
        if _is_missing_value(block.get(field_name), expected):
            missing.append(field_path)
    return missing


def evaluate_research_trigger(
    *,
    conflict: str,
    agent_results: Dict[str, Dict[str, Any]],
    data_quality_gate: Dict[str, Any] | None = None,
) -> ResearchTriggerDecision:
    _ = conflict
    if not RESEARCH_TRIGGER_ENABLED:
        return ResearchTriggerDecision(triggered=False)

    reasons: List[ResearchTriggerReason] = []

    missing_fields = _collect_missing_required_fields(agent_results)
    if missing_fields:
        reasons.append(
            ResearchTriggerReason(
                trigger="missing_required_fields",
                detail=f"{len(missing_fields)} required fields missing",
                field_paths=missing_fields[:20],
                severity="high",
            )
        )

    stale_agents: List[str] = []
    uncertain_agents: List[str] = []
    scores: List[float] = []
    for agent_name, score_key in SCORE_KEYS:
        block = agent_results.get(agent_name)
        if not isinstance(block, dict):
            continue
        freshness = str(block.get("data_freshness") or "").strip().lower()
        if freshness in ("stale", "unavailable"):
            stale_agents.append(agent_name)
        dq = safe_float(block.get("dq_confidence"))
        if dq is not None and float(dq) < RESEARCH_TRIGGER_DQ_CONFIDENCE_MIN:
            uncertain_agents.append(agent_name)
        sv = safe_float(block.get(score_key))
        if sv is not None:
            scores.append(float(sv))

    if stale_agents:
        reasons.append(
            ResearchTriggerReason(
                trigger="stale_data",
                detail=f"{len(stale_agents)} agents marked stale/unavailable",
                field_paths=[f"{name}.data_freshness" for name in stale_agents[:20]],
                severity="medium",
            )
        )

    score_spread = 0.0
    if len(scores) >= 2:
        score_spread = max(scores) - min(scores)
        if score_spread >= RESEARCH_TRIGGER_SCORE_SPREAD:
            reasons.append(
                ResearchTriggerReason(
                    trigger="agent_conflict",
                    detail=f"score spread {score_spread:.1f} >= {RESEARCH_TRIGGER_SCORE_SPREAD:.1f}",
                    field_paths=[],
                    severity="high",
                )
            )

    gate_warnings = []
    if isinstance(data_quality_gate, dict):
        gate_warnings = data_quality_gate.get("quality_warnings") or []
    if uncertain_agents or (isinstance(gate_warnings, list) and len(gate_warnings) > 0):
        reasons.append(
            ResearchTriggerReason(
                trigger="high_uncertainty",
                detail="low dq_confidence and/or quality gate warnings",
                field_paths=[f"{name}.dq_confidence" for name in uncertain_agents[:20]],
                severity="medium",
            )
        )

    # Provenance coverage: when few agents expose public reference URLs, enrichments should focus on adding sources.
    prov_agents = 0
    prov_ok = 0
    for agent_name, _score_key in SCORE_KEYS:
        block = agent_results.get(agent_name)
        if not isinstance(block, dict):
            continue
        prov_agents += 1
        refs = block.get("provenance_refs") or []
        if isinstance(refs, list) and any(isinstance(u, str) and u.strip().startswith(("http://", "https://")) for u in refs):
            prov_ok += 1
    provenance_coverage = (prov_ok / prov_agents) if prov_agents else 0.0
    if prov_agents and provenance_coverage < RESEARCH_TRIGGER_PROVENANCE_MIN:
        reasons.append(
            ResearchTriggerReason(
                trigger="low_provenance_coverage",
                detail=f"provenance coverage {provenance_coverage:.2f} < {RESEARCH_TRIGGER_PROVENANCE_MIN:.2f}",
                field_paths=[f"{name}.provenance_refs" for name, _ in SCORE_KEYS[:20]],
                severity="medium",
            )
        )

    triggered = len(reasons) >= max(1, RESEARCH_TRIGGER_MIN_REASONS)
    return ResearchTriggerDecision(
        triggered=triggered,
        reasons=reasons,
        missing_required_fields_count=len(missing_fields),
        stale_agents=stale_agents,
        uncertainty_agents=uncertain_agents,
        score_spread=round(score_spread, 2),
        provenance_coverage=round(provenance_coverage, 3),
    )
