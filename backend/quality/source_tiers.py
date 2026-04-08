"""
Source reliability tiers (institutional → social/unverified).
Maps feed names, domains, and agent source labels to a trust score in [0.2, 1.0].
"""

from __future__ import annotations

import re
from typing import Optional

# Tier midpoints: Tier1 0.95, Tier2 0.8, Tier3 0.6, Tier4 0.35
TIER1_KEYWORDS = (
    "reuters",
    "associated press",
    "ap news",
    "ap.org",
    "acled",
    "iaea",
    "international atomic energy",
)
TIER2_KEYWORDS = (
    "eia",
    "fred",
    "greynoise",
    "ads-b",
    "adsb",
    "opensky",
    "bbc",
    "al jazeera",
    "the guardian",
    "nytimes",
    "washington post",
    "ft.com",
    "bloomberg",
    "politico",
    "foreign policy",
    "defense news",
)
TIER3_KEYWORDS = (
    "gdelt",
    "newsapi",
    "gnews",
    "newsdata",
    "rss",
    "google news",
    "aggregat",
)
TIER4_KEYWORDS = (
    "telegram",
    "reddit",
    "twitter",
    "x.com",
    "social",
    "socmint",
)


def _lower(s: str) -> str:
    return (s or "").strip().lower()


def trust_for_source_name(name: Optional[str], *, default: float = 0.55) -> float:
    """
    Return trust score for a human-readable source name or URL fragment.
    """
    n = _lower(name or "")
    if not n:
        return default

    if any(k in n for k in TIER1_KEYWORDS):
        return 0.95
    if any(k in n for k in TIER2_KEYWORDS):
        return 0.8
    if any(k in n for k in TIER3_KEYWORDS):
        return 0.6
    if any(k in n for k in TIER4_KEYWORDS):
        return 0.35

    # Domain-like strings
    if re.search(r"\.(gov|int)(/|$)", n):
        return 0.85

    return default


def trust_for_agent_source(agent: str, source_hint: Optional[str] = None) -> float:
    """Combine agent family with optional per-item source string."""
    a = _lower(agent)
    base = 0.55
    if a in ("news", "diplo", "geoint"):
        base = 0.65
    if a in ("socmint", "narrative"):
        base = 0.4
    if source_hint:
        return max(base * 0.85, min(1.0, trust_for_source_name(source_hint, default=base)))
    return base
