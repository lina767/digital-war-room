"""
Agent-run heartbeat: structured in-memory history for ops (last run, 24h error rate, source reachability).

Process lifetime only; thread-safe. Populated from DAGScheduler after each registry agent node.
"""

from __future__ import annotations

import threading
import time
import math
from collections import deque
from typing import Any, Dict, List, Optional

# Keep enough history for 24h error rate at high frequency; prune by age.
_MAX_EVENTS = 20000
_RETAIN_SEC = 86400 * 2

_lock = threading.Lock()
_events: deque[tuple[float, Dict[str, Any]]] = deque(maxlen=_MAX_EVENTS)


def _prune_old() -> None:
    cutoff = time.time() - _RETAIN_SEC
    while _events and _events[0][0] < cutoff:
        _events.popleft()


def record_agent_heartbeat(
    *,
    agent: str,
    conflict: str,
    cycle_id: str,
    outcome: str,
    duration_ms: float,
    sources_ok_ratio: Optional[float],
    sources: List[Dict[str, Any]],
) -> None:
    """Append one heartbeat row and emit structured log for log aggregators."""
    entry = {
        "agent": agent,
        "conflict": conflict,
        "cycle_id": cycle_id,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
        "sources_ok_ratio": sources_ok_ratio,
        "sources": sources[:40],
    }
    ts = time.time()
    with _lock:
        _prune_old()
        _events.append((ts, entry))

    try:
        from observability import get_logger

        get_logger(__name__).info(
            "agent_heartbeat",
            agent=agent,
            conflict=conflict or None,
            cycle_id=cycle_id or None,
            outcome=outcome,
            duration_ms=round(duration_ms, 2),
            sources_ok_ratio=sources_ok_ratio,
            sources_count=len(sources),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).info(
            "agent_heartbeat agent=%s outcome=%s duration_ms=%.1f sources_n=%d",
            agent,
            outcome,
            duration_ms,
            len(sources),
        )


def _events_in_window(window_sec: float) -> List[tuple[float, Dict[str, Any]]]:
    cutoff = time.time() - window_sec
    with _lock:
        _prune_old()
        return [(ts, e) for ts, e in _events if ts >= cutoff]


def _error_rate_for_agent(agent: str, window_sec: float = 86400.0) -> Optional[float]:
    rows = [e for ts, e in _events_in_window(window_sec) if e.get("agent") == agent]
    if not rows:
        return None
    failed = sum(1 for e in rows if e.get("outcome") == "failed")
    return round(failed / len(rows), 4)


def _last_successful(agent: str) -> Optional[Dict[str, Any]]:
    """Last run with outcome ok or degraded (completed without hard failure)."""
    with _lock:
        _prune_old()
        for ts, e in reversed(list(_events)):
            if e.get("agent") != agent:
                continue
            if e.get("outcome") in ("ok", "degraded"):
                return {
                    "at": ts,
                    "at_iso": _iso(ts),
                    "conflict": e.get("conflict"),
                    "outcome": e.get("outcome"),
                    "duration_ms": e.get("duration_ms"),
                    "sources_ok_ratio": e.get("sources_ok_ratio"),
                }
    return None


def _last_run(agent: str) -> Optional[Dict[str, Any]]:
    with _lock:
        _prune_old()
        for ts, e in reversed(list(_events)):
            if e.get("agent") != agent:
                continue
            return {
                "at": ts,
                "at_iso": _iso(ts),
                "conflict": e.get("conflict"),
                "outcome": e.get("outcome"),
                "duration_ms": e.get("duration_ms"),
                "sources_ok_ratio": e.get("sources_ok_ratio"),
            }
    return None


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def get_ops_snapshot() -> Dict[str, Any]:
    """
    Per registry agent: last run, last non-failed run, 24h error rate, last source snapshot, Haiku quota slice.
    """
    from agents.registry import get_agent_registry
    from services.haiku_service import get_haiku_metrics_for_api

    agents_out: List[Dict[str, Any]] = []
    haiku = get_haiku_metrics_for_api()
    month_by = haiku.get("month_by_agent") or {}
    last_run_haiku = (haiku.get("last_run") or {}).get("by_agent") or {}

    for desc in get_agent_registry().all_agents():
        name = desc.name
        err_24h = _error_rate_for_agent(name, 86400.0)
        agents_out.append(
            {
                "agent": name,
                "division": desc.division,
                "last_run": _last_run(name),
                "last_successful_run": _last_successful(name),
                "error_rate_24h": err_24h,
                "runs_24h_sample": _run_count_24h(name),
                "duration_stats_24h": _duration_stats_for_agent(name, 86400.0),
                "quota": {
                    "haiku_month_tokens": month_by.get(name),
                    "haiku_last_run_tokens": last_run_haiku.get(name),
                },
            }
        )

    return {
        "generated_at": time.time(),
        "generated_at_iso": _iso(time.time()),
        "window_error_rate_sec": 86400,
        "agents": agents_out,
        "anthropic_haiku_global": {
            "month_budget_usd": haiku.get("month_budget_usd"),
            "month_spent_usd": haiku.get("month_spent_usd"),
            "model": haiku.get("model"),
        },
        "quota_note": "Haiku usage is tracked per agent; most external REST APIs do not expose remaining quota via this backend.",
    }


def _run_count_24h(agent: str) -> int:
    return len([1 for (_, e) in _events_in_window(86400.0) if e.get("agent") == agent])


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(float(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    rank = (max(0.0, min(100.0, p)) / 100.0) * (len(vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return vals[lo]
    weight = rank - lo
    return vals[lo] * (1.0 - weight) + vals[hi] * weight


def _duration_stats_for_agent(agent: str, window_sec: float = 86400.0) -> Dict[str, Any]:
    rows = [e for _, e in _events_in_window(window_sec) if e.get("agent") == agent]
    durations = []
    for e in rows:
        try:
            durations.append(float(e.get("duration_ms")))
        except (TypeError, ValueError):
            continue
    p50 = _percentile(durations, 50.0)
    p95 = _percentile(durations, 95.0)
    return {
        "window_sec": int(window_sec),
        "samples": len(durations),
        "p50_ms": round(p50, 2) if p50 is not None else None,
        "p95_ms": round(p95, 2) if p95 is not None else None,
        "max_ms": round(max(durations), 2) if durations else None,
    }
