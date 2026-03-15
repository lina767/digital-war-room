"""
Lightweight predictive layer for escalation and markets.

Deliberately coarse: works with ordinal levels (LOW…CRITICAL) and optional
probability ranges instead of pretending to have precise probabilities.
"""
from typing import Any, Dict, List, Literal, Optional, TypedDict


PredictiveLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PredictiveBasis = Literal["baseline", "data", "markets", "mixed"]
PredictiveConfidence = Literal["LOW", "MEDIUM", "HIGH"]


class ProbabilityRange(TypedDict, total=False):
    min: float  # 0.0–1.0, e.g. 0.6
    max: float  # 0.0–1.0, e.g. 0.8


class EscalationForecast(TypedDict, total=False):
    horizon: str                   # e.g. "24h", "7d"
    level: PredictiveLevel
    range: ProbabilityRange
    basis: PredictiveBasis
    confidence: PredictiveConfidence
    drivers: List[str]
    vs_baseline: Literal["higher", "similar", "lower"]
    notes: Optional[str]


class MarketForecast(TypedDict, total=False):
    instrument: str
    horizon: str
    level: PredictiveLevel
    direction: Literal["UP", "DOWN", "FLAT"]
    range: ProbabilityRange
    basis: PredictiveBasis
    confidence: PredictiveConfidence
    drivers: List[str]
    vs_baseline: Literal["higher", "similar", "lower"]
    notes: Optional[str]


class PredictiveBlock(TypedDict, total=False):
    baseline_escalation: EscalationForecast
    escalation: List[EscalationForecast]
    markets: List[MarketForecast]
    market_benchmark: List[MarketForecast]


def _level_from_score(score: float) -> PredictiveLevel:
    """Map escalation score 0–100 to ordinal level."""
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _range_from_level(level: PredictiveLevel) -> ProbabilityRange:
    """
    Coarse probability band per level.

    Deliberately wide; communication aides, not calibrated probabilities.
    """
    if level == "CRITICAL":
        return {"min": 0.65, "max": 0.85}
    if level == "HIGH":
        return {"min": 0.45, "max": 0.65}
    if level == "MEDIUM":
        return {"min": 0.25, "max": 0.45}
    return {"min": 0.05, "max": 0.25}


def _compare_levels(current: PredictiveLevel, baseline: PredictiveLevel) -> Literal["higher", "similar", "lower"]:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if order[current] > order[baseline]:
        return "higher"
    if order[current] < order[baseline]:
        return "lower"
    return "similar"


# ── Conflict-specific baselines ───────────────────────────────────────────────
# Active conflicts and regions under sustained tensions get a higher baseline
# than a peacetime default. This prevents absurd "LOW baseline" for warzones.
CONFLICT_BASELINES: Dict[str, PredictiveLevel] = {
    "iran":     "HIGH",
    "us-iran":  "HIGH",
    "ukraine":  "HIGH",
    "russia":   "HIGH",
    "israel":   "HIGH",
    "gaza":     "CRITICAL",
    "syria":    "MEDIUM",
    "taiwan":   "MEDIUM",
    "north korea": "MEDIUM",
}
DEFAULT_BASELINE: PredictiveLevel = "LOW"


def _get_conflict_baseline(conflict: str) -> PredictiveLevel:
    """Return the baseline escalation level for a given conflict."""
    cl = (conflict or "").lower()
    for key, level in CONFLICT_BASELINES.items():
        if key in cl:
            return level
    return DEFAULT_BASELINE


def _compute_escalation_score(combined_score: float, agent_scores: Dict[str, float]) -> float:
    """
    Compute an escalation-oriented score that doesn't get dampened by quiet agents.

    The supervisor's combined_score is a weighted average across all 11 agents.
    If 3 agents scream (GEOINT=100, NEWS=90, SOCMINT=84) but 8 others are calm,
    the average lands around 40–55 → MEDIUM. That's misleading in a crisis.

    This function uses max(combined_score, peak_weighted) where peak_weighted
    gives 60% weight to the top-3 agents and 40% to the combined average.
    """
    scores = sorted(agent_scores.values(), reverse=True)
    if not scores:
        return combined_score

    top3_avg = sum(scores[:3]) / min(3, len(scores))
    peak_weighted = top3_avg * 0.6 + combined_score * 0.4
    return max(combined_score, peak_weighted)


def build_predictive_block(conflict: str, combined_score: float, agent_scores: Dict[str, float]) -> PredictiveBlock:
    """
    Build predictive block from supervisor scores and per-agent scores.

    Uses conflict-specific baselines and a peak-weighted escalation score
    that reflects crisis signals from top agents instead of being dampened
    by quiet agents.
    """
    baseline_level = _get_conflict_baseline(conflict)
    baseline_range = _range_from_level(baseline_level)

    baseline_drivers = []
    if baseline_level in ("HIGH", "CRITICAL"):
        baseline_drivers.append(f"Active conflict region – baseline elevated to {baseline_level}.")
    else:
        baseline_drivers.append("No sustained conflict history; peacetime baseline.")

    baseline: EscalationForecast = {
        "horizon": "7d",
        "level": baseline_level,
        "range": baseline_range,
        "basis": "baseline",
        "confidence": "MEDIUM",
        "drivers": baseline_drivers,
        "vs_baseline": "similar",
        "notes": f"Conflict-calibrated baseline for '{conflict}'.",
    }

    escalation_score = _compute_escalation_score(combined_score, agent_scores)
    level_24h = _level_from_score(escalation_score)
    range_24h = _range_from_level(level_24h)
    vs_baseline = _compare_levels(level_24h, baseline_level)

    top_streams = sorted(agent_scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
    driver_labels = [f"{name.upper()} score {score:.1f}" for name, score in top_streams if score > 0]
    if not driver_labels:
        driver_labels = ["No strong escalation indicators across agents."]

    confidence: PredictiveConfidence = "HIGH" if len([s for s in agent_scores.values() if s > 0]) >= 5 else "MEDIUM"

    escalation_24h: EscalationForecast = {
        "horizon": "24h",
        "level": level_24h,
        "range": range_24h,
        "basis": "data",
        "confidence": confidence,
        "drivers": driver_labels,
        "vs_baseline": vs_baseline,
        "notes": f"Peak-weighted score {escalation_score:.0f} (combined avg {combined_score:.0f}).",
    }

    # 7d uses same score/level as 24h; horizon is for display/planning only.
    escalation_7d: EscalationForecast = {
        "horizon": "7d",
        "level": level_24h,
        "range": range_24h,
        "basis": "data",
        "confidence": confidence,
        "drivers": driver_labels,
        "vs_baseline": vs_baseline,
        "notes": f"Same escalation score as 24h ({escalation_score:.0f}); 7d horizon for medium-term outlook.",
    }

    predictive: PredictiveBlock = {
        "baseline_escalation": baseline,
        "escalation": [escalation_24h, escalation_7d],
        "markets": [],
        "market_benchmark": [],
    }
    return predictive

