"""Outcome classification and source snapshot for agent heartbeat (used from DAGScheduler)."""

from typing import Any, Dict, List, Optional, Tuple

from .health_registry import get_health_registry


def classify_agent_outcome(result: Any, *, timed_out: bool, exec_failed: bool) -> str:
    """ok = normal result; degraded = fallback path; failed = timeout, exception, or hard error."""
    if timed_out or exec_failed:
        return "failed"
    if not isinstance(result, dict):
        return "ok"
    if result.get("timeout_or_error") is True:
        return "failed"
    meta = result.get("_meta") or {}
    if meta.get("timeout_or_error") is True:
        return "failed"
    err = result.get("error")
    if isinstance(err, str) and err.strip():
        return "failed"
    if meta.get("fallback_used") is True:
        return "degraded"
    return "ok"


def sources_for_agent_snapshot(agent_name: str) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    """Availability-style summary for this agent's sources from HealthRegistry (current run)."""
    reg = get_health_registry()
    if reg is None:
        return None, []
    report = reg.get_health_report()
    srcs = [s for s in report.get("sources", []) if s.get("agent") == agent_name]
    if not srcs:
        return None, []
    ok_n = sum(1 for s in srcs if s.get("status") == "ok")
    ratio = round(ok_n / len(srcs), 4)
    slim = [
        {
            "source": s.get("source"),
            "status": s.get("status"),
            "availability_pct": s.get("availability_pct"),
            "circuit_open": s.get("circuit_open"),
            "last_error": s.get("last_error"),
        }
        for s in srcs[:24]
    ]
    return ratio, slim
