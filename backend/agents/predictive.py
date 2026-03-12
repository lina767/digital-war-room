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
    """Map composite escalation_score 0–100 to ordinal level."""
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _range_from_level(level: PredictiveLevel) -> ProbabilityRange:
    """
    Very coarse probability band per level.

    We keep these deliberately wide; they are meant as communication aides,
    not calibrated probabilities.
    """
    if level == "CRITICAL":
        return {"min": 0.6, "max": 0.8}
    if level == "HIGH":
        return {"min": 0.4, "max": 0.6}
    if level == "MEDIUM":
        return {"min": 0.2, "max": 0.4}
    return {"min": 0.05, "max": 0.2}


def _compare_levels(current: PredictiveLevel, baseline: PredictiveLevel) -> Literal["higher", "similar", "lower"]:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if order[current] > order[baseline]:
        return "higher"
    if order[current] < order[baseline]:
        return "lower"
    return "similar"


def build_predictive_block(conflict: str, combined_score: float, agent_scores: Dict[str, float]) -> PredictiveBlock:
    """
    Build minimal predictive block from existing supervisor composite score and per-stream scores.

    MVP: one baseline hypothesis and one 24h-forecast for escalation.
    Markets block is left empty for now (Phase 1 focuses on escalation).
    """
    # Baseline: peace-time / low-intensity expectation; in späteren Phasen
    # können wir diese pro Konflikt kalibrieren (z. B. anhand historischer Daten).
    baseline_level: PredictiveLevel = "LOW"
    baseline_range = _range_from_level(baseline_level)
    baseline: EscalationForecast = {
        "horizon": "7d",
        "level": baseline_level,
        "range": baseline_range,
        "basis": "baseline",
        "confidence": "MEDIUM",
        "drivers": ["Historical baseline only (no current escalation signals applied)."],
        "vs_baseline": "similar",
        "notes": f"Null-hypothesis baseline for conflict '{conflict}'. To be calibrated with real event frequencies.",
    }

    # Data-informed forecast for the next 24 hours based on composite score.
    level_24h = _level_from_score(combined_score)
    range_24h = _range_from_level(level_24h)
    vs_baseline = _compare_levels(level_24h, baseline_level)

    # Simple drivers: name the main contributing streams by score.
    top_streams = sorted(agent_scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
    driver_labels = [f"{name.upper()} score {score:.1f}" for name, score in top_streams if score > 0]
    if not driver_labels:
        driver_labels = ["No strong escalation indicators across agents."]

    escalation_24h: EscalationForecast = {
        "horizon": "24h",
        "level": level_24h,
        "range": range_24h,
        "basis": "data",
        "confidence": "MEDIUM",
        "drivers": driver_labels,
        "vs_baseline": vs_baseline,
        "notes": "Rule-based aggregation of existing agent scores; no LLM calibration yet.",
    }

    predictive: PredictiveBlock = {
        "baseline_escalation": baseline,
        "escalation": [escalation_24h],
        "markets": [],
        "market_benchmark": [],
    }
    return predictive

