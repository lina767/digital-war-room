"""CEO synthesis constants: legacy agent weights, division weights, LLM payload limits."""

from typing import Dict

# Legacy supervisor: per-agent weights (sum 1.0). Excluded when data_confidence=degraded (renormalized).
CEO_LEGACY_AGENT_WEIGHTS: Dict[str, float] = {
    "finint": 0.09,
    "sigint": 0.11,
    "news": 0.08,
    "geoint": 0.05,
    "satintel": 0.05,
    "socmint": 0.07,
    "mediaint": 0.035,
    "techint": 0.07,
    "cyber": 0.07,
    "energy": 0.06,
    "protest": 0.07,
    "diplo": 0.06,
    "proximity": 0.08,
    "chokepoint": 0.095,
    "pentagon": 0.01,
}

# CEO-level division weights
CEO_WEIGHTS: Dict[str, float] = {
    "military": 0.30,
    "financial": 0.18,
    "information": 0.22,
    "political": 0.14,
    "technical": 0.16,
}

MAX_PAYLOAD_CHARS = 250_000
