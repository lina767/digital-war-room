import os
from typing import Any, Dict, List

from ..utils import safe_float


def _polymarket_sentiment_bonus(probs: List[float]) -> float:
    """Crowd-implied escalation from Polymarket: primary Stimmungs-/Erwartungsindikator vs. Metaculus/Kalshi.

    Uses max probability (strongest implied risk) plus a small breadth term when several
    markets align. Tunable via FININT_POLYMARKET_WEIGHT_MULT (default 1.0).
    """
    if not probs:
        return 0.0
    try:
        mult = float((os.getenv("FININT_POLYMARKET_WEIGHT_MULT") or "1.0").strip())
    except (TypeError, ValueError):
        mult = 1.0
    mult = max(0.5, min(2.0, mult))

    max_prob = max(probs)
    mean_prob = sum(probs) / len(probs)
    raw = 0.0
    if max_prob > 0.55:
        raw += 30.0
    elif max_prob > 0.42:
        raw += 22.0
    elif max_prob > 0.28:
        raw += 14.0
    elif max_prob > 0.15:
        raw += 7.0
    if len(probs) >= 3 and mean_prob > 0.35:
        raw += 10.0
    elif len(probs) >= 2 and mean_prob > 0.32:
        raw += 5.0
    return round(raw * mult, 2)


def compute_finint_escalation_score(
    brent: Dict[str, Any],
    vix: Dict[str, Any],
    fear_greed: Dict[str, Any],
    polymarket_list: List[Dict[str, Any]],
    metaculus_list: List[Dict[str, Any]],
    kalshi_list: List[Dict[str, Any]],
    ofac: Dict[str, Any],
) -> float:
    """Compute FININT escalation score in range 0-100."""
    base = 50.0

    if isinstance(brent, dict) and "error" not in brent and brent.get("change_pct"):
        cp = brent.get("change_pct") or "0%"
        if "+" in cp and "%" in cp:
            try:
                v = float(cp.replace("%", "").strip())
                if v > 5:
                    base += 15
                elif v > 2:
                    base += 8
            except ValueError:
                pass
        if "-" in cp:
            base -= 10

    if polymarket_list:
        pm_probs = [
            (safe_float(p.get("probability")) or 0)
            for p in polymarket_list
            if isinstance(p, dict) and "error" not in p
        ]
        pm_probs = [x for x in pm_probs if x > 0]
        base += _polymarket_sentiment_bonus(pm_probs)

    if metaculus_list:
        meta_probs = [
            safe_float(p.get("probability"))
            for p in metaculus_list
            if isinstance(p, dict) and "error" not in p and p.get("probability") is not None
        ]
        if meta_probs:
            max_meta = max(meta_probs)
            if max_meta and max_meta > 0.5:
                base += 8
            elif max_meta and max_meta > 0.3:
                base += 4

    if kalshi_list:
        kalshi_probs = [
            safe_float(p.get("probability"))
            for p in kalshi_list
            if isinstance(p, dict) and "error" not in p and p.get("probability") is not None
        ]
        if kalshi_probs and max(kalshi_probs) > 0.5:
            base += 5

    ofac_total = int(ofac.get("total_matches") or 0) if isinstance(ofac, dict) and "error" not in ofac else 0
    if ofac_total > 200:
        base += 6
    elif ofac_total > 50:
        base += 3

    vix_price = safe_float(vix.get("price")) if isinstance(vix, dict) and "error" not in vix else None
    if vix_price is not None and vix_price > 25:
        base += 2

    fg_val = fear_greed.get("value") if isinstance(fear_greed, dict) and "error" not in fear_greed else None
    if fg_val is not None and fg_val <= 25:
        base += 2

    return max(0.0, min(100.0, base))
