"""
Cross-agent corroboration layer for finding candidates.

Runs after parallel agent collection and before supervisor synthesis.
It groups semantically similar findings into event clusters and annotates each
candidate with a deterministic score adjustment:
- bonus when independent agents/upstreams corroborate the same event
- penalty for weak single-source claims (notably single GDELT-only rows)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

from .finding_signal_gate import FindingCandidate

_STOPWORDS: Set[str] = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "with",
    "from",
    "into",
    "after",
    "before",
    "over",
    "under",
    "about",
    "this",
    "that",
    "is",
    "are",
    "was",
    "were",
    "be",
    "to",
    "of",
    "in",
    "on",
    "at",
}


def _event_text(raw: str) -> str:
    t = (raw or "").strip()
    if "–" in t:
        return t.split("–", 1)[1].strip().lower()
    return t.lower()


def _tokens(text: str) -> Set[str]:
    parts = re.findall(r"[a-z0-9]{3,}", _event_text(text))
    return {p for p in parts if p not in _STOPWORDS}


def _location_tokens(text: str) -> Set[str]:
    t = _event_text(text)
    # Simple location-ish capture after common prepositions.
    loc = re.findall(r"\b(?:in|near|at)\s+([a-z][a-z0-9\-]{2,})\b", t)
    return {x.strip().lower() for x in loc if x.strip()}


def _time_tokens(text: str) -> Set[str]:
    t = _event_text(text)
    tokens = set()
    for kw in ("today", "tonight", "yesterday", "now", "this week", "24h", "48h"):
        if kw in t:
            tokens.add(kw)
    if re.search(r"\b\d{1,2}:\d{2}\b", t):
        tokens.add("clock_time")
    return tokens


def _domain(url: Any) -> str:
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        from urllib.parse import urlparse

        return (urlparse(url.strip()).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def _source_key(s: Dict[str, Any]) -> str:
    name = str(s.get("name") or s.get("source") or "").lower().strip()
    kind = str(s.get("kind") or "").lower().strip()
    dom = _domain(s.get("url"))
    if "gdelt" in name or kind == "gdelt":
        return "aggregator:gdelt"
    if "acled" in name or "acled" in kind:
        return "aggregator:acled"
    if dom:
        return f"domain:{dom}"
    if name:
        return f"name:{name[:80]}"
    return "unknown"


def _similar(
    a: Set[str],
    b: Set[str],
    a_loc: Set[str],
    b_loc: Set[str],
    a_time: Set[str],
    b_time: Set[str],
) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    if inter < 2:
        return False
    union = len(a | b) or 1
    j = inter / union
    loc_overlap = bool(a_loc and b_loc and (a_loc & b_loc))
    time_overlap = bool(a_time and b_time and (a_time & b_time))
    if j >= 0.5:
        return True
    # Medium lexical similarity must be anchored by location or time.
    return j >= 0.33 and (loc_overlap or time_overlap)


def _single_gdelt_only(c: FindingCandidate) -> bool:
    if len(set(c.agents or [])) != 1:
        return False
    src = c.sources or []
    if len(src) != 1:
        return False
    s0 = src[0] if isinstance(src[0], dict) else {}
    key = _source_key(s0)
    return key == "aggregator:gdelt"


def apply_cross_agent_corroboration(candidates: List[FindingCandidate]) -> Tuple[List[FindingCandidate], Dict[str, Any]]:
    """
    Annotate candidates with corroboration adjustment in metadata.
    Returns (updated_candidates, meta).
    """
    if not candidates:
        return [], {"events": 0, "corroborated_events": 0, "single_source_downgrades": 0}

    toks = [_tokens(c.text) for c in candidates]
    locs = [_location_tokens(c.text) for c in candidates]
    times = [_time_tokens(c.text) for c in candidates]
    n = len(candidates)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if _similar(toks[i], toks[j], locs[i], locs[j], times[i], times[j]):
                union(i, j)

    clusters: Dict[int, List[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    updated: List[FindingCandidate] = []
    corroborated_events = 0
    single_source_downgrades = 0

    cluster_meta: Dict[int, Dict[str, Any]] = {}
    for root, idxs in clusters.items():
        agents = set()
        upstreams = set()
        for idx in idxs:
            c = candidates[idx]
            agents.update({str(a).lower().strip() for a in (c.agents or []) if str(a).strip()})
            for s in (c.sources or []):
                if isinstance(s, dict):
                    upstreams.add(_source_key(s))
        cluster_meta[root] = {
            "size": len(idxs),
            "agents": sorted(agents),
            "upstreams": sorted(upstreams),
        }
        if len(agents) >= 2 and len(upstreams) >= 2:
            corroborated_events += 1

    for i, c in enumerate(candidates):
        root = find(i)
        cm = cluster_meta.get(root, {})
        independent_agents = len(cm.get("agents") or [])
        independent_upstreams = len(cm.get("upstreams") or [])

        bonus = 0.0
        if independent_agents >= 2:
            bonus += min(0.2, 0.08 * (independent_agents - 1))
        if independent_upstreams >= 2:
            bonus += min(0.12, 0.04 * (independent_upstreams - 1))

        penalty = 0.0
        if _single_gdelt_only(c):
            penalty = 0.2
            single_source_downgrades += 1
        elif independent_agents == 1 and len(c.sources or []) <= 1:
            penalty = 0.1

        adj = max(-0.35, min(0.35, bonus - penalty))
        md = dict(c.metadata or {})
        md["corroboration_event"] = {
            "cluster_size": int(cm.get("size") or 1),
            "independent_agents": independent_agents,
            "independent_upstreams": independent_upstreams,
            "bonus": round(bonus, 4),
            "penalty": round(penalty, 4),
        }
        md["corroboration_adjustment"] = round(adj, 4)
        updated.append(FindingCandidate(text=c.text, sources=c.sources, agents=c.agents, metadata=md))

    meta = {
        "events": len(clusters),
        "corroborated_events": corroborated_events,
        "single_source_downgrades": single_source_downgrades,
    }
    return updated, meta

