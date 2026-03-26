"""CEO score aggregation, threat mapping, and contradiction heuristics."""

import os
from typing import Any, Dict, List, Tuple

from .ceo_config import CEO_LEGACY_AGENT_WEIGHTS


def coerce_float(value: Any, default: float = 0.0) -> float:
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


def legacy_combined_excluding_degraded(
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


def degraded_streams_caveat(degraded_agents: List[str]) -> str:
    labels = ", ".join(a.upper() for a in degraded_agents)
    return (
        f"Data caveat: degraded streams (no reliable feed) for {labels} — "
        "treat those scores as unknown; low values reflect missing data, not evidence of safety."
    )


def threat_level_from_score(synthesis_score: float) -> str:
    if synthesis_score >= 80:
        return "CRITICAL"
    if synthesis_score >= 60:
        return "HIGH"
    if synthesis_score >= 40:
        return "ELEVATED"
    if synthesis_score >= 20:
        return "LOW"
    return "MINIMAL"


def agents_seem_contradictory(scores: List[float]) -> bool:
    if len(scores) < 2:
        return False
    threshold = float(os.getenv("SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD", "50"))
    return (max(scores) - min(scores)) >= threshold
