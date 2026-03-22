"""
Shared utilities for all backend agents.
Eliminates duplication of common helpers across sigint, finint, geoint, news agents.
"""

import asyncio
import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Per-agent signal quality for synthesis (not the same as statistical confidence).
# degraded = no usable primary/proxy feed — numeric scores must not be read as "all clear".
DataConfidenceLevel = Literal["live", "estimated", "degraded"]

logger = logging.getLogger(__name__)

# Shared pool for run_async fallback (when asyncio.run() can't be used).
_ASYNC_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="async-runner")


def run_async(coro):
    """Run an async coroutine from synchronous code.

    Works even when an event loop is already running in the current thread
    (Python 3.13 ThreadPoolExecutor edge case). Falls back to executing
    ``asyncio.run()`` in a separate clean thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = _ASYNC_POOL.submit(asyncio.run, coro)
    return future.result(timeout=120)


# ── Type-safe conversions ─────────────────────────────────────────────────


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """Convert to float, returning *default* on failure (None if not given)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── LLM response cleaning ────────────────────────────────────────────────


def strip_llm_json(text: str) -> str:
    """Remove ```json / ``` wrappers that LLMs add around JSON."""
    text = text.strip()
    for prefix in ("```json", "```"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    """Strip LLM markdown fences, parse JSON. Returns None on failure."""
    cleaned = strip_llm_json(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


# ── ADS-B response normalisation ─────────────────────────────────────────


def parse_adsb_response(data: Any) -> List[Dict[str, Any]]:
    """Normalise the various ADS-B JSON shapes into a flat aircraft list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("ac") or data.get("aircraft") or []
    return []


# ── Shared Pydantic models ───────────────────────────────────────────────


class ScoreConfidence(BaseModel):
    """Confidence metadata attached to every agent score."""

    level: str = "low"
    sources_ok: List[str] = Field(default_factory=list)
    sources_missing: List[str] = Field(default_factory=list)


class SourceResult(BaseModel):
    """Per-source fetch result for telemetry and health tracking."""

    name: str
    status: Literal["ok", "degraded", "error"]
    fetched_at: Optional[str] = None  # ISO-8601
    duration_ms: Optional[int] = None
    record_count: Optional[int] = None
    error: Optional[str] = None
    cached: bool = False


class AgentMetadata(BaseModel):
    """Standard metadata attached to every agent result (returned as _meta)."""

    agent: str
    fetched_at: str  # ISO-8601, when agent run started
    duration_ms: int
    sources: List[SourceResult]
    confidence: ScoreConfidence
    data_freshness: Literal["live", "recent", "stale", "unavailable"]
    data_confidence: DataConfidenceLevel = "estimated"
    fallback_used: bool = False
    error_summary: Optional[str] = None


def compute_confidence_from_sources(source_results: List[SourceResult]) -> ScoreConfidence:
    """Compute ScoreConfidence from a list of SourceResult (ok vs error ratio)."""
    if not source_results:
        return ScoreConfidence(level="low", sources_ok=[], sources_missing=[])
    ok = [s for s in source_results if s.status == "ok"]
    failed = [s for s in source_results if s.status == "error"]
    degraded = [s for s in source_results if s.status == "degraded"]
    total = len(source_results)
    ok_count = len(ok) + len(degraded)  # degraded counts as partial
    ratio = ok_count / total if total else 0
    if ratio >= 0.8:
        level = "high"
    elif ratio >= 0.5:
        level = "medium"
    else:
        level = "low"
    return ScoreConfidence(
        level=level,
        sources_ok=[s.name for s in ok] + [f"{s.name}(degraded)" for s in degraded],
        sources_missing=[s.name for s in failed],
    )


def data_freshness_from_sources(
    source_results: List[SourceResult],
    has_any_data: bool = True,
) -> Literal["live", "recent", "stale", "unavailable"]:
    """Derive data_freshness from source results and whether any data was returned."""
    ok_count = sum(1 for s in source_results if s.status == "ok")
    if ok_count >= 2:
        return "live"
    if ok_count >= 1:
        return "recent"
    if has_any_data:
        return "stale"
    return "unavailable"


def build_agent_meta(
    agent: str,
    fetched_at: str,
    duration_ms: int,
    source_results: List[SourceResult],
    *,
    fallback_used: bool = False,
    error_summary: Optional[str] = None,
    has_any_data: bool = True,
    confidence: Optional[ScoreConfidence] = None,
    data_confidence: Optional[DataConfidenceLevel] = None,
) -> Dict[str, Any]:
    """Build the _meta dict for an agent result (confidence + data_freshness from source_results).

    If *confidence* is set (e.g. FININT merges SourceResult health with per-key API status),
    it is used instead of compute_confidence_from_sources(source_results).

    *data_confidence* (live / estimated / degraded) may be set explicitly; otherwise it is
    inferred from freshness and whether any data was returned.
    """
    confidence_used = confidence if confidence is not None else compute_confidence_from_sources(source_results)
    data_freshness = data_freshness_from_sources(source_results, has_any_data=has_any_data)
    if data_confidence is None:
        if fallback_used or (data_freshness == "unavailable" and not has_any_data):
            data_confidence = "degraded"
        elif data_freshness == "live":
            data_confidence = "live"
        else:
            data_confidence = "estimated"
    meta = AgentMetadata(
        agent=agent,
        fetched_at=fetched_at,
        duration_ms=duration_ms,
        sources=source_results,
        confidence=confidence_used,
        data_freshness=data_freshness,
        data_confidence=data_confidence,
        fallback_used=fallback_used,
        error_summary=error_summary,
    )
    return meta.model_dump(mode="json")


def infer_data_confidence_from_result(result: Optional[Dict[str, Any]]) -> DataConfidenceLevel:
    """Best-effort data_confidence for CEO weighting and supervisor copy.

    Prefer explicit ``data_confidence`` on the payload or ``_meta.data_confidence``;
    otherwise derive from ``_meta`` (fallback, freshness).
    """
    if not result:
        return "degraded"
    explicit = result.get("data_confidence")
    if explicit in ("live", "estimated", "degraded"):
        return explicit  # type: ignore[return-value]
    meta = result.get("_meta")
    if isinstance(meta, dict):
        dc = meta.get("data_confidence")
        if dc in ("live", "estimated", "degraded"):
            return dc  # type: ignore[return-value]
        if meta.get("fallback_used"):
            return "degraded"
        if meta.get("data_freshness") == "unavailable":
            return "degraded"
        if meta.get("data_freshness") == "live":
            return "live"
    return "estimated"
