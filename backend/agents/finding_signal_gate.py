"""
Finding signal gate.

Goal: reduce noise before CEO synthesis by scoring candidate findings on:
- corroboration (independent confirmation)
- novelty (vs recent 72h embeddings)
- actionability (actor + timeframe + location)

The gate is designed to be:
- best-effort (never crashes synthesis)
- cheap (small Haiku JSON call per finding, capped)
- persistent (stores accepted+rejected embeddings for novelty checks when DB available)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .utils import parse_llm_json, utc_now_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FindingCandidate:
    text: str
    sources: List[Dict[str, Any]]
    agents: List[str]
    metadata: Dict[str, Any]


def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def _now_utc() -> str:
    return utc_now_iso()


def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        netloc = urlparse(url).netloc or ""
        return netloc.lower().replace("www.", "") if netloc else ""
    except Exception:
        return ""


def _source_upstream_key(source: Dict[str, Any]) -> str:
    """
    Coarse upstream identity for independence checks.
    We intentionally collapse common aggregators (NewsAPI/GDELT/ACLED) to avoid false corroboration.
    """
    name = str(source.get("name") or source.get("source") or "").lower().strip()
    agent = str(source.get("agent") or "").lower().strip()
    url = str(source.get("url") or "").strip()
    dom = _domain_from_url(url)

    # Normalize known aggregator families.
    # Note: this list is intentionally conservative; configurable overrides exist via env.
    if any(k in name for k in ("gdelt", "gkg")):
        return "aggregator:gdelt"
    if "acled" in name:
        return "aggregator:acled"
    if "newsapi" in name:
        return "aggregator:newsapi"
    if agent == "socmint":
        # Telegram / Twitter / Reddit channels are treated as distinct upstreams.
        src = str(source.get("source") or source.get("name") or "")
        return f"soc:{src.lower()[:80]}" if src else "soc:unknown"
    if dom:
        return f"domain:{dom}"
    if name:
        return f"name:{name[:80]}"
    return f"agent:{agent or 'unknown'}"


def _load_json_env(name: str, default: Any) -> Any:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return default


def _collapse_upstream(upstream: str, collapse_rules: Dict[str, str]) -> str:
    """
    Collapse upstream identifiers into equivalence classes to avoid false corroboration
    (e.g. multiple sources pulling from the same upstream wire/aggregator).
    collapse_rules is a map: substring/prefix -> canonical upstream.
    """
    u = (upstream or "").lower().strip()
    if not u:
        return ""
    for k, v in (collapse_rules or {}).items():
        kk = str(k).lower().strip()
        if not kk:
            continue
        if u.startswith(kk) or kk in u:
            return str(v).lower().strip() or u
    return u


def _heuristic_actionability(text: str) -> float:
    """
    Fast local heuristic: actor + time + location-ish.
    Returns a rough 0..1 prior; Haiku will refine if available.
    """
    t = text.lower()
    actor = bool(re.search(r"\b(irgc|idf|hamas|hezbollah|rsf|saf|wagner|isw|un|icj|ofac|eu)\b", t))
    time_ref = bool(re.search(r"\b(today|tonight|yesterday|this week|24h|hours?|utc|\d{1,2}:\d{2})\b", t))
    loc = bool(re.search(r"\b(in|near|at)\s+[a-z][a-z\-]{2,}\b", t)) or bool(re.search(r"\b(lat|lon)\b", t))
    score = 0.2
    score += 0.3 if actor else 0.0
    score += 0.3 if time_ref else 0.0
    score += 0.2 if loc else 0.0
    return min(1.0, score)


async def _novelty_score(
    *,
    finding_text: str,
    conflict: str,
    hours: int = 72,
    threshold: float = 0.75,
) -> Tuple[float, List[Dict[str, Any]], Optional[List[float]]]:
    """
    Novelty = 1 - max_similarity_vs_recent, best-effort.
    Returns (novelty_score, similar_items_preview).
    """
    try:
        from services.hf_service import embed
        from services.storage_service import find_similar_recent, is_available
    except Exception:
        return 0.5, [], None

    embeddings = await embed([finding_text[:600]])
    if not embeddings or not embeddings[0]:
        return 0.5, [], None
    emb: List[float] = embeddings[0]

    similar: List[Dict[str, Any]] = []
    if is_available():
        similar = await find_similar_recent(
            emb,
            top_k=5,
            source="finding_archive",
            conflict=conflict or None,
            threshold=threshold,
            max_age_hours=hours,
        )

    max_sim = max((float(s.get("similarity") or 0.0) for s in similar), default=0.0)
    novelty = 1.0 - max_sim
    return _clamp01(novelty), similar, emb


async def _haiku_score_dimensions(
    *,
    finding: FindingCandidate,
    recent_similar: List[Dict[str, Any]],
    usage_agent: str = "ceo",
) -> Optional[Dict[str, float]]:
    """
    Haiku JSON scoring for the 3 dimensions. Returns dict or None.
    """
    try:
        from services.haiku_service import analyst_summary
    except Exception:
        return None

    # Keep the baseline short but meaningful.
    baseline_lines = []
    for s in (recent_similar or [])[:4]:
        prev = str(s.get("text_preview") or "").strip()
        sim = s.get("similarity")
        if prev:
            baseline_lines.append(f"- ({sim:.2f}) {prev[:180]}")
    baseline = "\n".join(baseline_lines) if baseline_lines else "(none)"

    sources_compact = []
    for s in (finding.sources or [])[:10]:
        sources_compact.append(
            {
                "agent": s.get("agent"),
                "name": s.get("name") or s.get("source"),
                "url": s.get("url"),
                "upstream": _source_upstream_key(s),
            }
        )

    system = (
        "Score the finding on three dimensions (0.0-1.0):\n"
        "1) CORROBORATION: How many independent sources confirm this?\n"
        "   0.0 = single source; 0.5 = two sources but same upstream; 1.0 = 2+ independent sources.\n"
        "2) NOVELTY: Is this substantively new vs. the recent baseline provided?\n"
        "3) ACTIONABILITY: Does it name a specific actor, timeframe, and location?\n\n"
        "Return ONLY valid JSON: "
        '{"corroboration": <float>, "novelty": <float>, "actionability": <float>}'
    )
    user = (
        f"Finding:\n{finding.text}\n\n"
        f"Recent baseline (last 72h, nearest neighbors):\n{baseline}\n\n"
        f"Source metadata:\n{json.dumps(sources_compact, ensure_ascii=False)}"
    )

    raw = await analyst_summary(system=system, data=user, max_tokens=220, usage_agent=usage_agent)
    if not raw:
        return None
    parsed = parse_llm_json(raw)
    if not isinstance(parsed, dict):
        return None

    return {
        "corroboration": _clamp01(parsed.get("corroboration")),
        "novelty": _clamp01(parsed.get("novelty")),
        "actionability": _clamp01(parsed.get("actionability")),
    }


def _corroboration_from_sources(f: FindingCandidate) -> float:
    """
    Deterministic corroboration prior based on upstream diversity across sources+agents.
    """
    collapse_rules = _load_json_env(
        "FINDING_SIGNAL_GATE_UPSTREAM_COLLAPSE_JSON",
        {
            "aggregator:acled": "upstream:acled",
            "aggregator:gdelt": "upstream:gdelt",
            "aggregator:newsapi": "upstream:newsapi",
            "domain:news.google.com": "upstream:google_news",
        },
    )

    up = set()
    for s in f.sources or []:
        up.add(_collapse_upstream(_source_upstream_key(s), collapse_rules))
    for a in f.agents or []:
        up.add(_collapse_upstream(f"agent:{str(a).lower()}", collapse_rules))

    # Heuristic mapping:
    if len(up) <= 1:
        return 0.0
    if len(up) == 2:
        # Could still be same upstream family (e.g. acled+gdelt).
        if any(x.startswith("aggregator:") for x in up):
            return 0.5
        return 0.7
    return 1.0


def _weighted_total(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    wsum = sum(weights.values()) or 1.0
    return (
        scores.get("corroboration", 0.0) * weights.get("corroboration", 0.0)
        + scores.get("novelty", 0.0) * weights.get("novelty", 0.0)
        + scores.get("actionability", 0.0) * weights.get("actionability", 0.0)
    ) / wsum


async def score_and_gate_findings(
    *,
    candidates: List[FindingCandidate],
    conflict: str,
    threshold: float = 0.7,
    weights: Optional[Dict[str, float]] = None,
    max_llm: int = 20,
) -> Dict[str, Any]:
    """
    Score candidates and split into high-signal vs archive.
    Returns:
      {
        "accepted": [{"text", "scores", "total", "sources", "agents"}],
        "archived": [{"text", "scores", "total", "sources", "agents"}],
        "meta": {...}
      }
    """
    if weights is None:
        weights = _load_json_env(
            "FINDING_SIGNAL_GATE_WEIGHTS_JSON",
            {"corroboration": 0.4, "novelty": 0.3, "actionability": 0.3},
        )
    if not isinstance(weights, dict):
        weights = {"corroboration": 0.4, "novelty": 0.3, "actionability": 0.3}
    threshold = float(threshold)
    max_llm = max(0, int(max_llm))

    out_ok = []
    out_low = []
    llm_used = 0
    started_at = datetime.now(timezone.utc).isoformat()

    # Score most actionable-ish first to spend LLM budget well.
    ordered = sorted(candidates or [], key=lambda c: _heuristic_actionability(c.text), reverse=True)

    for cand in ordered[:60]:
        novelty, similar, emb = await _novelty_score(finding_text=cand.text, conflict=conflict)
        base = {
            "corroboration": _corroboration_from_sources(cand),
            "novelty": novelty,
            "actionability": _heuristic_actionability(cand.text),
        }

        # Optional Haiku refinement (capped).
        refined = None
        if llm_used < max_llm and os.getenv("USE_FINDING_SIGNAL_GATE_LLM", "true").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            refined = await _haiku_score_dimensions(finding=cand, recent_similar=similar, usage_agent="ceo")
            if refined:
                llm_used += 1

        scores = refined or base
        total = _weighted_total(scores, weights)
        decision = "accepted" if total >= threshold else "archived"
        row = {
            "text": cand.text,
            "scores": {k: round(float(v), 4) for k, v in scores.items()},
            "total": round(float(total), 4),
            "sources": cand.sources,
            "agents": cand.agents,
            "decision": decision,
        }
        if decision == "accepted":
            out_ok.append(row)
        else:
            out_low.append(row)

        # Persist to pgvector as a dedicated namespace for later search.
        if emb:
            try:
                from services.storage_service import is_available, store_embedding

                if is_available():
                    await store_embedding(
                        cand.text[:2000],
                        emb,
                        source="finding_archive",
                        conflict=conflict,
                        metadata={
                            "kind": "finding_candidate",
                            "decision": decision,
                            "scores": {k: float(v) for k, v in scores.items()},
                            "total": float(total),
                            "agents": cand.agents,
                            "sources": cand.sources[:12],
                            "stored_at": _now_utc(),
                        },
                    )
            except Exception:
                pass

    out_ok.sort(key=lambda r: r.get("total", 0), reverse=True)
    out_low.sort(key=lambda r: r.get("total", 0), reverse=True)

    return {
        "accepted": out_ok,
        "archived": out_low,
        "meta": {
            "gate": "finding_signal_gate_v1",
            "started_at": started_at,
            "threshold": threshold,
            "weights": weights,
            "llm_used": llm_used,
            "candidates_in": len(candidates or []),
            "accepted_n": len(out_ok),
            "archived_n": len(out_low),
        },
    }

