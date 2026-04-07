"""
Data-quality contract for agent results (reliability / accuracy layer).

Aligned with the Data Quality Accuracy plan: every agent payload should expose
consistent quality attributes, either explicitly or derived from ``_meta``.

Field semantics (allowed values)
--------------------------------

**dq_confidence** (float, 0–100)
    Roll-up confidence that the agent’s numeric scores and lists are grounded
    in successfully fetched sources. Not the same as geopolitical “escalation”.

**data_freshness** (``"live"`` | ``"recent"`` | ``"stale"`` | ``"unavailable"``)
    How current the underlying feeds are, derived from ``_meta.sources`` and
    ``_meta.data_freshness`` when not set explicitly.

**source_count** (int)
    Number of source rows in ``_meta.sources`` (best-effort).

**fallback_used** (bool)
    True when the agent used contract fallback / error path (see ``_meta.fallback_used``).

**error_summary** (optional str)
    Short human-readable error from ``_meta.error_summary`` when present.

**provenance_refs** (list of str)
    Public reference URLs collected from ``_meta.sources[*].reference_urls`` (capped).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

DataFreshnessLevel = Literal["live", "recent", "stale", "unavailable"]


class AgentQualityFields(BaseModel):
    """Canonical optional quality fields mirrored on agent dicts (and BaseAgentResult)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    dq_confidence: float = Field(0.0, ge=0.0, le=100.0)
    data_freshness: DataFreshnessLevel = "unavailable"
    source_count: int = Field(0, ge=0)
    fallback_used: bool = False
    error_summary: str | None = None
    provenance_refs: List[str] = Field(default_factory=list)


def _level_to_dq_confidence(level: str | None, *, fallback_used: bool, data_freshness: str | None) -> float:
    base = {"high": 85.0, "medium": 55.0, "low": 25.0}.get((level or "").lower(), 30.0)
    if fallback_used:
        base = min(base, 20.0)
    if data_freshness == "unavailable":
        base = min(base, 25.0)
    elif data_freshness == "stale":
        base = min(base, base * 0.85)
    return max(0.0, min(100.0, base))


def sync_agent_quality_from_meta(agent_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Fill dq_* / provenance fields from ``_meta`` when missing or incomplete."""
    if not isinstance(agent_dict, dict):
        return {}
    meta = agent_dict.get("_meta")
    if not isinstance(meta, dict):
        meta = {}

    sources = meta.get("sources") or []
    n = len(sources) if isinstance(sources, list) else 0

    conf_block = meta.get("confidence") if isinstance(meta.get("confidence"), dict) else {}
    level = conf_block.get("level") if isinstance(conf_block, dict) else None

    fb = bool(meta.get("fallback_used"))
    freshness = meta.get("data_freshness")
    if freshness not in ("live", "recent", "stale", "unavailable"):
        freshness = "unavailable"

    dq = _level_to_dq_confidence(
        str(level) if level is not None else None,
        fallback_used=fb,
        data_freshness=freshness,
    )

    if agent_dict.get("source_count") in (None, 0) and n:
        agent_dict["source_count"] = n
    agent_dict.setdefault("dq_confidence", dq)
    agent_dict.setdefault("data_freshness", freshness)
    agent_dict.setdefault("fallback_used", fb)
    if agent_dict.get("error_summary") is None and meta.get("error_summary"):
        agent_dict["error_summary"] = str(meta.get("error_summary"))[:2000]

    if not agent_dict.get("provenance_refs"):
        refs: List[str] = []
        for s in sources if isinstance(sources, list) else []:
            if not isinstance(s, dict):
                continue
            for u in (s.get("reference_urls") or [])[:5]:
                if isinstance(u, str) and u.strip():
                    refs.append(u.strip())
            if len(refs) >= 25:
                break
        agent_dict["provenance_refs"] = refs[:25]

    return agent_dict


def apply_quality_to_all_agents(
    agent_results: Dict[str, Dict[str, Any]],
    *,
    keys: tuple[str, ...] | None = None,
) -> None:
    """Mutate agent dicts in place with ``sync_agent_quality_from_meta``."""
    names = keys or (
        "finint",
        "sigint",
        "news",
        "geoint",
        "satintel",
        "socmint",
        "mediaint",
        "techint",
        "cyber",
        "energy",
        "diplo",
        "proximity",
        "narrative",
        "chokepoint",
        "pentagon",
    )
    for name in names:
        block = agent_results.get(name)
        if isinstance(block, dict):
            sync_agent_quality_from_meta(block)
