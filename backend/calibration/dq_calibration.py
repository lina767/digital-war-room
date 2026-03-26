"""
Calibration metrics for confidence scores and agent reliability (monitoring / backtests).

Intended use: feed completed analysis dicts (from cache or audit) to compute aggregates;
compare over time to tune thresholds in ``quality_gate`` and supervisor weighting.
"""

from __future__ import annotations

from typing import Any, Dict, List

AGENT_NAMES = (
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
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
    "pentagon",
)


def compute_calibration_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive summary metrics for calibration dashboards from one analysis result dict.

    Does not require DB; safe on partial payloads.
    """
    if not isinstance(result, dict):
        return {"error": "not_a_dict"}

    degraded = result.get("degraded_agents") or []
    if not isinstance(degraded, list):
        degraded = []

    dq_conf_values: List[float] = []
    fb_agents: List[str] = []
    per_agent: Dict[str, Any] = {}

    for name in AGENT_NAMES:
        block = result.get(name)
        if not isinstance(block, dict):
            continue
        dq = block.get("dq_confidence")
        try:
            if dq is not None:
                dq_conf_values.append(float(dq))
        except (TypeError, ValueError):
            pass
        meta = block.get("_meta") if isinstance(block.get("_meta"), dict) else {}
        if meta.get("fallback_used"):
            fb_agents.append(name)
        per_agent[name] = {
            "dq_confidence": block.get("dq_confidence"),
            "data_freshness": block.get("data_freshness"),
            "fallback_used": bool(meta.get("fallback_used")),
            "data_confidence": meta.get("data_confidence"),
        }

    gate = result.get("data_quality_gate") if isinstance(result.get("data_quality_gate"), dict) else {}
    warnings = gate.get("quality_warnings") or []
    if not isinstance(warnings, list):
        warnings = []

    avg_dq = sum(dq_conf_values) / len(dq_conf_values) if dq_conf_values else None

    return {
        "calibration_schema_version": 1,
        "degraded_agent_count": len(degraded),
        "degraded_agents": list(degraded),
        "fallback_agent_count": len(fb_agents),
        "fallback_agents": fb_agents,
        "mean_dq_confidence": round(avg_dq, 2) if avg_dq is not None else None,
        "gate_confidence": gate.get("gate_confidence"),
        "quality_warning_count": len(warnings),
        "per_agent": per_agent,
    }
