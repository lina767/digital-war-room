"""
Shared state/cache helpers for API routes.
Used by routes_analyze and by main.py (push_* for recording analysis results).
"""

import os
from typing import Any, Dict, Optional

from fastapi import Request

from services.state_service import StateService

# Escalation timeline: keep last N points per conflict for "escalation over the day" UI.
ESCALATION_TIMELINE_MAX_POINTS = int(os.getenv("ESCALATION_TIMELINE_MAX_POINTS", "24"))

# Agent keys present in supervisor result (for status recording).
AGENT_KEYS = (
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
)

ANALYSIS_RUN_HISTORY_MAX = 50


def _get_state_service(request: Request) -> Optional[StateService]:
    return getattr(request.app.state, "state_service", None)


def get_state_service(request: Request) -> Optional[StateService]:
    """Return StateService from app state, or None (legacy in-memory fallback)."""
    return _get_state_service(request)


def get_cache(request: Request, conflict: Optional[str] = None) -> Any:
    """Return cache entry for conflict, or full cache dict if conflict is None."""
    state = _get_state_service(request)
    if state:
        if conflict is not None:
            return state.get_cache(conflict)
        return state.get_cache_all()
    if conflict is not None:
        return getattr(request.app.state, "analysis_cache", {}).get(conflict)
    return getattr(request.app.state, "analysis_cache", {})


def get_last_error(request: Request, conflict: Optional[str] = None) -> Any:
    state = _get_state_service(request)
    if state:
        if conflict is not None:
            return state.get_last_error(conflict)
        return state.get_last_error_all()
    d = getattr(request.app.state, "analysis_last_error", {})
    return d.get(conflict) if conflict is not None else d


def get_escalation_timeline(request: Request, conflict: Optional[str] = None) -> Any:
    state = _get_state_service(request)
    if state:
        if conflict is not None:
            return state.get_escalation_timeline(conflict)
        return state.get_escalation_timeline_all()
    d = getattr(request.app.state, "escalation_timeline_history", {})
    return d.get(conflict, []) if conflict is not None else d


def build_agent_status_from_result(result: dict) -> Dict[str, Dict[str, Any]]:
    """Build per-agent status dict from full analysis result."""
    status: Dict[str, Dict[str, Any]] = {}
    if not isinstance(result, dict):
        return status
    for key in AGENT_KEYS:
        agent_result = result.get(key)
        if not isinstance(agent_result, dict):
            status[key] = {"status": "ok"}
            continue
        if agent_result.get("timeout_or_error"):
            meta = agent_result.get("_meta") or {}
            status[key] = {
                "status": "error",
                "fetched_at": meta.get("fetched_at"),
                "duration_ms": meta.get("duration_ms"),
                "confidence": meta.get("confidence"),
                "data_freshness": meta.get("data_freshness"),
                "sources": meta.get("sources", []),
                "fallback_used": meta.get("fallback_used", False),
                "error_summary": meta.get("error_summary"),
            }
            continue
        meta = agent_result.get("_meta") or {}
        status[key] = {
            "status": "ok",
            "fetched_at": meta.get("fetched_at"),
            "duration_ms": meta.get("duration_ms"),
            "confidence": meta.get("confidence"),
            "data_freshness": meta.get("data_freshness"),
            "sources": meta.get("sources", []),
            "fallback_used": meta.get("fallback_used", False),
            "error_summary": meta.get("error_summary"),
        }
    return status


def push_agent_status(app_state, result: dict) -> None:
    """Record per-agent status from last analysis. Uses StateService when available."""
    state = getattr(app_state, "state_service", None)
    if state:
        state.set_agent_status_full(build_agent_status_from_result(result))
        return
    status = getattr(app_state, "agent_status_last", None)
    if status is None:
        return
    for k, v in build_agent_status_from_result(result).items():
        status[k] = v


def push_run_history(app_state, conflict: str, at_ts: float, result: dict) -> None:
    """Append one run summary. Uses StateService when available."""
    if not isinstance(result, dict):
        return
    per_agent = {}
    for key in AGENT_KEYS:
        agent_result = result.get(key)
        if isinstance(agent_result, dict):
            meta = agent_result.get("_meta") or {}
            per_agent[key] = {
                "duration_ms": meta.get("duration_ms"),
                "status": "error" if agent_result.get("timeout_or_error") else "ok",
            }
    entry = {
        "at": at_ts,
        "conflict": conflict,
        "escalation_score": result.get("escalation_score"),
        "agents": per_agent,
        "error": result.get("error")
        or (result.get("_run_error") if isinstance(result.get("_run_error"), str) else None),
    }
    state = getattr(app_state, "state_service", None)
    if state:
        state.push_run_history_entry(entry)
        return
    history = getattr(app_state, "analysis_run_history", None)
    if history is not None:
        history.append(entry)


def push_escalation_timeline(app_state, conflict: str, at_ts: float, result: dict) -> None:
    """Append one point to escalation timeline. Uses StateService when available."""
    score = None
    if isinstance(result, dict):
        score = result.get("escalation_score")
    if score is None:
        return
    try:
        score = float(score)
    except (TypeError, ValueError):
        return
    state = getattr(app_state, "state_service", None)
    if state:
        state.append_escalation_timeline(conflict, at_ts, score)
        return
    history = getattr(app_state, "escalation_timeline_history", None)
    if history is None:
        return
    if conflict not in history:
        history[conflict] = []
    history[conflict].append({"at": at_ts, "escalation_score": round(score, 1)})
    history[conflict] = history[conflict][-ESCALATION_TIMELINE_MAX_POINTS:]
