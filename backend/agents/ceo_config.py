"""CEO synthesis constants: legacy agent weights, division weights, LLM payload limits.

Weights can be overridden without code changes:
  CEO_LEGACY_AGENT_WEIGHTS_JSON='{"chokepoint":0.14,"news":0.10,"sigint":0.12}'
  CEO_DIVISION_WEIGHTS_JSON='{"military":0.35,"financial":0.15}'

Partial JSON merges into defaults; values are renormalized to sum to 1.0.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

# Legacy supervisor: per-agent weights (sum 1.0). Excluded when data_confidence=degraded (renormalized).
_DEFAULT_LEGACY_AGENT_WEIGHTS: Dict[str, float] = {
    "finint": 0.09,
    "sigint": 0.11,
    "news": 0.08,
    "geoint": 0.05,
    "satintel": 0.05,
    "socmint": 0.07,
    "techint": 0.07,
    "cyber": 0.07,
    "energy": 0.06,
    "diplo": 0.06,
    "proximity": 0.08,
    "chokepoint": 0.095,
    "pentagon": 0.01,
}

# CEO-level division weights (sum 1.0)
_DEFAULT_CEO_DIVISION_WEIGHTS: Dict[str, float] = {
    "military": 0.30,
    "financial": 0.18,
    "information": 0.22,
    "political": 0.14,
    "technical": 0.16,
}

MAX_PAYLOAD_CHARS = 250_000
_ENV_LEGACY = "CEO_LEGACY_AGENT_WEIGHTS_JSON"
_ENV_DIVISION = "CEO_DIVISION_WEIGHTS_JSON"


def _normalize_weights(weights: Dict[str, float], fallback: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in weights.values())
    if total <= 0:
        return dict(fallback)
    return {k: max(0.0, v) / total for k, v in weights.items()}


def _merge_weight_dict(
    base: Dict[str, float],
    env_name: str,
) -> Dict[str, float]:
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return dict(base)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(
            "%s invalid JSON (%s); using default weights",
            env_name,
            e,
        )
        return dict(base)
    if not isinstance(data, dict):
        logger.warning("%s must be a JSON object; using defaults", env_name)
        return dict(base)
    out = dict(base)
    for k, v in data.items():
        if k not in base:
            continue
        try:
            fv = float(v)
            if fv >= 0:
                out[k] = fv
        except (TypeError, ValueError):
            continue
    return _normalize_weights(out, base)


CEO_LEGACY_AGENT_WEIGHTS: Dict[str, float] = _merge_weight_dict(
    _DEFAULT_LEGACY_AGENT_WEIGHTS,
    _ENV_LEGACY,
)
CEO_WEIGHTS: Dict[str, float] = _merge_weight_dict(
    _DEFAULT_CEO_DIVISION_WEIGHTS,
    _ENV_DIVISION,
)
