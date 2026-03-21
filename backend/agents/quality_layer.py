"""
Central quality scoring and multi-source fusion for numeric datapoints.

Pilot: FININT Brent/WTI — Alpha Vantage and FRED fetched in parallel, fused with
weighted median, conflict detection, and a small provenance chain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from .utils import safe_float

ReliabilityTier = Literal["official", "curated", "community"]

# Lowercase source ids after normalisation
FININT_SOURCE_PROFILE: Dict[str, Tuple[ReliabilityTier, float]] = {
    "fred": ("official", 1.0),
    "alpha_vantage": ("curated", 0.88),
    "metals_api": ("curated", 0.82),
    "alternative_me": ("community", 0.55),
    "polymarket": ("community", 0.6),
    "metaculus": ("curated", 0.75),
}


class DataPoint(BaseModel):
    """Single observation with quality metadata (API / fusion output)."""

    value: float
    source: str
    reliability: ReliabilityTier
    freshness_minutes: float = 0.0
    corroboration: int = 0
    confidence: float = Field(ge=0, le=100)
    conflict_flag: Optional[str] = None


class ProvenanceStep(BaseModel):
    source: str
    value: float
    reliability: ReliabilityTier
    weight_effective: float
    fetched_at: Optional[str] = None


class FusionResult(BaseModel):
    value: float
    fused_display: str
    confidence: float = Field(ge=0, le=100)
    corroboration: int = 0
    conflict_flag: Optional[str] = None
    method: str = "weighted_median"
    provenance: List[ProvenanceStep] = Field(default_factory=list)


def normalise_source_id(source: str) -> str:
    return (source or "").lower().strip().replace(" ", "_").replace("-", "_")


def profile_for_source(source_id: str) -> Tuple[ReliabilityTier, float]:
    key = normalise_source_id(source_id)
    return FININT_SOURCE_PROFILE.get(key, ("community", 0.5))


def minutes_since_iso(iso_ts: Optional[str], now: Optional[datetime] = None) -> float:
    if not iso_ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ref = now or datetime.now(timezone.utc)
        return max(0.0, (ref - dt).total_seconds() / 60.0)
    except Exception:
        return 0.0


def freshness_decay_weight(minutes: float, half_life_minutes: float = 240.0) -> float:
    if half_life_minutes <= 0:
        return 1.0
    return 0.5 ** (minutes / half_life_minutes)


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return float(values[0])
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total_w = sum(weights)
    if total_w <= 0:
        return float(sum(values) / len(values))
    half = total_w / 2.0
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= half:
            return float(v)
    return float(pairs[-1][0])


def detect_spread_conflict(values: Sequence[float], relative_threshold: float = 0.035) -> Optional[str]:
    if len(values) < 2:
        return None
    lo, hi = min(values), max(values)
    mid = (lo + hi) / 2.0
    if mid <= 0:
        return "price_spread" if hi - lo > 1e-6 else None
    if (hi - lo) / abs(mid) > relative_threshold:
        return "price_spread"
    return None


def corroboration_count(values: Sequence[float], fused: float, relative_threshold: float = 0.02) -> int:
    if not values:
        return 0
    if abs(fused) < 1e-12:
        return sum(1 for v in values if abs(v - fused) < 1e-9)
    return sum(1 for v in values if abs(v - fused) / abs(fused) <= relative_threshold)


def _confidence_score(
    tiers: Sequence[ReliabilityTier],
    corroboration: int,
    n_sources: int,
    conflict: Optional[str],
    max_freshness_minutes: float,
) -> float:
    base = 52.0
    if "official" in tiers:
        base += 18.0
    elif "curated" in tiers:
        base += 10.0
    if n_sources >= 2 and corroboration >= 2:
        base += 14.0
    elif n_sources >= 1:
        base += 4.0
    if conflict:
        base -= 22.0
    # stale run (all observations old) — soft penalty
    if max_freshness_minutes > 720:
        base -= 8.0
    return max(0.0, min(100.0, base))


def fuse_numeric_observations(
    observations: List[Dict[str, Any]],
    *,
    relative_spread_threshold: float = 0.035,
    half_life_minutes: float = 240.0,
) -> FusionResult:
    """
    Fuse several numeric observations (each must have float `value`, str `source`, optional `fetched_at`).

    Extra keys (change_pct, as_of) are ignored here — caller picks display fields from the heaviest source.
    """
    rows: List[Tuple[float, str, ReliabilityTier, float, str, Optional[str]]] = []
    for o in observations:
        v = o.get("value")
        if isinstance(v, str):
            v = safe_float(v)
        if v is None:
            continue
        src = str(o.get("source") or "unknown")
        tier, base_w = profile_for_source(src)
        ft = o.get("fetched_at")
        ft_s = ft if isinstance(ft, str) else None
        mins = minutes_since_iso(ft_s)
        w_eff = base_w * freshness_decay_weight(mins, half_life_minutes=half_life_minutes)
        rows.append((float(v), src, tier, w_eff, normalise_source_id(src), ft_s))

    if not rows:
        return FusionResult(value=float("nan"), fused_display="", confidence=0.0, corroboration=0)

    values = [r[0] for r in rows]
    weights = [r[3] for r in rows]
    fused = weighted_median(values, weights)
    conflict = detect_spread_conflict(values, relative_threshold=relative_spread_threshold)
    corr = corroboration_count(values, fused)
    tiers = [r[2] for r in rows]
    max_fresh = max((minutes_since_iso(r[5]) for r in rows if r[5]), default=0.0)
    conf = _confidence_score(tiers, corr, len(rows), conflict, max_fresh)

    prov = [
        ProvenanceStep(
            source=r[1],
            value=r[0],
            reliability=r[2],
            weight_effective=round(r[3], 4),
            fetched_at=r[5],
        )
        for r in rows
    ]

    return FusionResult(
        value=fused,
        fused_display=f"{fused:.2f}",
        confidence=round(conf, 1),
        corroboration=corr,
        conflict_flag=conflict,
        provenance=prov,
    )


def pick_display_fields(
    observations: List[Dict[str, Any]],
    provenance: Sequence[ProvenanceStep],
) -> Tuple[str, str, str]:
    """Return change_pct, as_of from the observation whose source matches max weight_effective in provenance."""
    if not observations or not provenance:
        return "0.0%", "", ""
    best = max(provenance, key=lambda p: p.weight_effective)
    best_src = normalise_source_id(best.source)
    for o in observations:
        if normalise_source_id(str(o.get("source") or "")) == best_src:
            cp = o.get("change_pct")
            ao = o.get("as_of")
            return (
                str(cp) if cp is not None else "0.0%",
                str(ao) if ao is not None else "",
                str(o.get("fetched_at") or ""),
            )
    o0 = observations[0]
    return (
        str(o0.get("change_pct") or "0.0%"),
        str(o0.get("as_of") or ""),
        str(o0.get("fetched_at") or ""),
    )


def build_quality_payload(fusion: FusionResult, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact JSON-safe structure for FININT brent/wti `quality` field."""
    change_pct, as_of, primary_fetched_at = pick_display_fields(observations, fusion.provenance)
    primary_src = None
    if fusion.provenance:
        primary_src = max(fusion.provenance, key=lambda p: p.weight_effective).source
    return {
        "fusion_method": fusion.method,
        "confidence": fusion.confidence,
        "corroboration": fusion.corroboration,
        "conflict_flag": fusion.conflict_flag,
        "primary_change_from": primary_src,
        "change_pct": change_pct,
        "as_of": as_of,
        "fused_at": primary_fetched_at,
        "provenance": [p.model_dump(mode="json") for p in fusion.provenance],
    }
