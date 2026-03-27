"""Research enrichment normalizer with hard source enforcement."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from .research_contracts import ResearchEnrichmentItem


def _valid_source_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _set_field_path(target: Dict[str, Any], field_path: str, value: Any) -> bool:
    parts = [p for p in field_path.split(".") if p]
    if len(parts) < 2:
        return False
    current: Dict[str, Any] = target
    for p in parts[:-1]:
        nxt = current.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            current[p] = nxt
        current = nxt
    current[parts[-1]] = value
    return True


def normalize_research_enrichments(
    raw_items: List[Dict[str, Any]] | None,
) -> Tuple[List[ResearchEnrichmentItem], List[Dict[str, Any]], float]:
    """Return (applied, rejected, source_coverage_ratio)."""
    if not isinstance(raw_items, list):
        return [], [], 0.0
    applied: List[ResearchEnrichmentItem] = []
    rejected: List[Dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            rejected.append({"reason": "invalid_item_type", "item": raw})
            continue
        if not _valid_source_url(raw.get("source_url")):
            rejected.append({"reason": "missing_or_invalid_source_url", "item": raw})
            continue
        try:
            item = ResearchEnrichmentItem.model_validate(raw)
            applied.append(item)
        except Exception as exc:
            rejected.append({"reason": f"contract_validation_failed:{type(exc).__name__}", "item": raw})

    total = len(applied) + len(rejected)
    ratio = (len(applied) / total) if total > 0 else 0.0
    return applied, rejected, ratio


def apply_research_enrichments(agent_results: Dict[str, Dict[str, Any]], applied: List[ResearchEnrichmentItem]) -> int:
    """Mutates agent_results in-place. Returns number of applied assignments."""
    n = 0
    for item in applied:
        if _set_field_path(agent_results, item.field_path, item.value):
            n += 1
    return n


def apply_research_enrichments_from_raw(
    agent_results: Dict[str, Dict[str, Any]],
    raw_items: List[Dict[str, Any]] | None,
) -> int:
    applied, _, _ = normalize_research_enrichments(raw_items)
    return apply_research_enrichments(agent_results, applied)
