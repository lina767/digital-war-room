"""
Cross-agent quality gate: plausibility and consistency checks before CEO synthesis.

Runs on raw agent dicts after collection. Output is attached to the analysis result
as ``data_quality_gate`` and passed into the supervisor LLM payload as
``data_quality_gate`` so the model can down-rank contradictory streams.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.config import DQ_QUALITY_GATE_ENABLED, DQ_SCORE_SPREAD_WARN_THRESHOLD
from agents.utils import safe_float

GATE_VERSION = 1


def _coerce_score(agent: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in agent:
            v = safe_float(agent.get(k))
            if v is not None:
                return float(v)
    return None


def _check_geo_coords(agent: Dict[str, Any], agent_name: str) -> List[str]:
    warnings: List[str] = []
    for label, items in (
        ("ships", agent.get("ships") or []),
        ("aircraft", agent.get("aircraft") or []),
    ):
        if not isinstance(items, list):
            continue
        bad = 0
        for it in items[:200]:
            if not isinstance(it, dict) or "error" in it:
                continue
            lat, lon = it.get("lat"), it.get("lon")
            if lat is None or lon is None:
                continue
            try:
                lf, lg = float(lat), float(lon)
            except (TypeError, ValueError):
                bad += 1
                continue
            if not (-90.0 <= lf <= 90.0 and -180.0 <= lg <= 180.0):
                bad += 1
        if bad:
            warnings.append(f"{agent_name}.{label}: {bad} items with out-of-range or invalid lat/lon")
    return warnings


def _finint_quality_warnings(finint: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ("brent", "wti"):
        block = finint.get(key)
        if not isinstance(block, dict):
            continue
        q = block.get("quality")
        if isinstance(q, dict) and q.get("conflict_flag"):
            out.append(f"finint.{key}: fused price conflict_flag={q.get('conflict_flag')}")
    return out


def run_cross_agent_quality_gate(
    conflict: str,
    agent_results: Dict[str, Dict[str, Any]],
    *,
    quality_fusion: Optional[Dict[str, Any]] = None,
    synthesis_score: float = 0.0,
) -> Dict[str, Any]:
    """
    Return structured gate result: warnings, aggregate confidence, per-check flags.

    *quality_fusion* is the store output from ``quality_fusion`` DAG node (optional).
    """
    _ = conflict  # reserved for region-specific rules
    warnings: List[str] = []
    checks: Dict[str, Any] = {}

    scores: Dict[str, float] = {}
    for name, keys in (
        ("finint", ("escalation_score",)),
        ("sigint", ("sigint_score",)),
        ("news", ("news_score",)),
        ("geoint", ("geoint_score",)),
        ("satintel", ("satintel_score",)),
        ("socmint", ("socmint_score",)),
        ("techint", ("techint_score",)),
        ("cyber", ("cyber_score",)),
        ("energy", ("energy_score",)),
        ("protest", ("protest_score",)),
        ("diplo", ("diplo_score",)),
        ("proximity", ("proximity_score",)),
        ("chokepoint", ("chokepoint_score",)),
        ("pentagon", ("pentagon_score",)),
    ):
        ag = agent_results.get(name) or {}
        if not isinstance(ag, dict):
            continue
        sc = _coerce_score(ag, *keys)
        if sc is not None:
            scores[name] = sc

    spread_threshold = DQ_SCORE_SPREAD_WARN_THRESHOLD
    if len(scores) >= 2:
        hi, lo = max(scores.values()), min(scores.values())
        spread = hi - lo
        checks["score_spread"] = round(spread, 2)
        if spread >= spread_threshold:
            warnings.append(
                f"Large cross-agent score spread ({spread:.1f}); treat single-stream spikes with caution."
            )

    news_s = scores.get("news")
    geo_s = scores.get("geoint")
    if news_s is not None and geo_s is not None:
        delta = abs(news_s - geo_s)
        checks["news_geoint_delta"] = round(delta, 2)
        if delta >= spread_threshold:
            warnings.append(
                f"NEWS vs GEOINT score gap {delta:.1f} — possible narrative vs thermal mismatch; verify primary sources."
            )

    sigint = agent_results.get("sigint") or {}
    if isinstance(sigint, dict):
        warnings.extend(_check_geo_coords(sigint, "sigint"))

    finint = agent_results.get("finint") or {}
    if isinstance(finint, dict):
        warnings.extend(_finint_quality_warnings(finint))

    cp = agent_results.get("chokepoint") or {}
    if isinstance(cp, dict):
        dc = cp.get("data_confidence")
        cscore = _coerce_score(cp, "chokepoint_score")
        if dc == "degraded" and cscore is not None and cscore >= 70:
            warnings.append("Chokepoint score is high while data_confidence is degraded; treat as uncertain.")

    qf = quality_fusion if isinstance(quality_fusion, dict) else {}
    fusion_err = (qf.get("fusion_meta") or {}).get("error") if isinstance(qf.get("fusion_meta"), dict) else None
    if fusion_err:
        warnings.append(f"quality_fusion node error: {fusion_err}")
        checks["quality_fusion_ok"] = False
    else:
        checks["quality_fusion_ok"] = True

    # Aggregate gate confidence from per-agent dq_confidence (post-sync)
    dq_vals: List[float] = []
    for name in scores:
        ag = agent_results.get(name)
        if isinstance(ag, dict):
            dq = safe_float(ag.get("dq_confidence"))
            if dq is not None:
                dq_vals.append(float(dq))
    gate_confidence = sum(dq_vals) / len(dq_vals) if dq_vals else 40.0
    gate_confidence = max(0.0, min(100.0, gate_confidence - 5.0 * len(warnings)))

    return {
        "gate_version": GATE_VERSION,
        "quality_warnings": warnings,
        "gate_confidence": round(gate_confidence, 1),
        "checks": checks,
        "synthesis_score_at_gate": round(float(synthesis_score), 2),
    }


def quality_gate_enabled() -> bool:
    return DQ_QUALITY_GATE_ENABLED
