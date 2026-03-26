"""
In-memory monitoring data for the Agent Monitor UI: error log, fallback counters,
and daily Haiku spend rollups. Thread-safe; process lifetime only.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from models.analysis_contract import AGENT_KEYS
from services.privacy_sanitize import mask_emails_in_text

ERROR_LOG_MAX = 400
DAILY_HISTORY_MAX = 45

_lock = threading.Lock()
_errors: List[Dict[str, Any]] = []

_fallback_total = 0
_fallback_by_agent: Dict[str, int] = defaultdict(int)
_last_fallback_run: Optional[Dict[str, Any]] = None

# Data-quality aggregates (process lifetime, thread-safe)
_dq_runs_total = 0
_dq_warning_total = 0
_dq_last: Optional[Dict[str, Any]] = None

# day (YYYY-MM-DD) -> {spend_usd, input_tokens, output_tokens, by_agent: {agent: {in,out}}}
_daily_haiku: Dict[str, Dict[str, Any]] = {}
_daily_order: List[str] = []


def _prune_errors() -> None:
    global _errors
    while len(_errors) > ERROR_LOG_MAX:
        _errors.pop(0)


def record_error(
    *,
    message: str,
    severity: str = "error",
    agent: Optional[str] = None,
    source: Optional[str] = None,
    conflict: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Append one error / warning row for the monitor UI."""
    if not message or not str(message).strip():
        return
    entry = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "severity": severity,
        "agent": agent,
        "source": source,
        "conflict": conflict,
        "message": mask_emails_in_text(str(message).strip()[:2000]),
        "detail": (mask_emails_in_text(detail.strip()[:8000]) if detail else None),
    }
    with _lock:
        _errors.append(entry)
        _prune_errors()


def record_dq_from_analysis(conflict: str, result: Dict[str, Any]) -> None:
    """Record data-quality gate summary from a completed analysis (best-effort)."""
    global _dq_runs_total, _dq_warning_total, _dq_last
    if not isinstance(result, dict):
        return
    gate = result.get("data_quality_gate")
    if not isinstance(gate, dict):
        return
    warnings = gate.get("quality_warnings") or []
    n_warn = len(warnings) if isinstance(warnings, list) else 0
    with _lock:
        _dq_runs_total += 1
        _dq_warning_total += n_warn
        _dq_last = {
            "conflict": conflict,
            "at": time.time(),
            "gate_confidence": gate.get("gate_confidence"),
            "quality_warning_count": n_warn,
            "checks": gate.get("checks"),
        }


def record_from_analysis(conflict: str, result: Dict[str, Any]) -> None:
    """Derive fallback tallies and agent errors from a completed analysis result."""
    global _fallback_total, _last_fallback_run
    if not isinstance(result, dict):
        return

    run_err = result.get("error")
    if run_err is None and isinstance(result.get("_run_error"), str):
        run_err = result.get("_run_error")
    if isinstance(run_err, str) and run_err.strip():
        record_error(
            message=run_err.strip()[:2000],
            severity="error",
            agent="supervisor",
            conflict=conflict,
            detail=None,
        )

    fb_agents: List[str] = []
    for key in AGENT_KEYS:
        agent_result = result.get(key)
        if not isinstance(agent_result, dict):
            continue
        meta = agent_result.get("_meta") or {}
        if meta.get("fallback_used"):
            fb_agents.append(key)
            with _lock:
                _fallback_total += 1
                _fallback_by_agent[key] += 1

        if agent_result.get("timeout_or_error"):
            summary = meta.get("error_summary")
            if isinstance(summary, str) and summary.strip():
                record_error(
                    message=summary.strip()[:2000],
                    severity="error",
                    agent=key,
                    conflict=conflict,
                    detail=agent_result.get("error") if isinstance(agent_result.get("error"), str) else None,
                )
            else:
                err = agent_result.get("error")
                record_error(
                    message=(str(err) if err else "timeout_or_error"),
                    severity="error",
                    agent=key,
                    conflict=conflict,
                )

    with _lock:
        _last_fallback_run = {
            "conflict": conflict,
            "at": time.time(),
            "agents": fb_agents,
            "count": len(fb_agents),
        }

    try:
        record_dq_from_analysis(conflict, result)
    except Exception:
        pass


def record_haiku_daily(
    *,
    day: str,
    spend_usd: float,
    input_tokens: int,
    output_tokens: int,
    by_agent: Dict[str, Dict[str, int]],
) -> None:
    """Merge one analysis run into the daily Haiku bucket (UTC day key)."""
    with _lock:
        if day not in _daily_haiku:
            _daily_haiku[day] = {
                "spend_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "by_agent": defaultdict(lambda: {"in": 0, "out": 0}),
            }
            _daily_order.append(day)
            while len(_daily_order) > DAILY_HISTORY_MAX:
                old = _daily_order.pop(0)
                _daily_haiku.pop(old, None)

        bucket = _daily_haiku[day]
        bucket["spend_usd"] = float(bucket["spend_usd"]) + float(spend_usd)
        bucket["input_tokens"] = int(bucket["input_tokens"]) + int(input_tokens)
        bucket["output_tokens"] = int(bucket["output_tokens"]) + int(output_tokens)
        ba = bucket["by_agent"]
        for agent, vals in by_agent.items():
            if agent not in ba:
                ba[agent] = {"in": 0, "out": 0}
            ba[agent]["in"] += int(vals.get("in", 0))
            ba[agent]["out"] += int(vals.get("out", 0))


def list_errors(limit: int = 100) -> List[Dict[str, Any]]:
    with _lock:
        return list(reversed(_errors[-limit:]))


def get_snapshot() -> Dict[str, Any]:
    """Aggregated monitoring payload (fallback, errors, daily Haiku rollups). Route merges Haiku totals."""
    with _lock:
        fb_by_agent = dict(_fallback_by_agent)
        err_tail = list(reversed(_errors[-ERROR_LOG_MAX:]))
        daily_out: List[Dict[str, Any]] = []
        for d in sorted(_daily_order, reverse=True)[:DAILY_HISTORY_MAX]:
            b = _daily_haiku.get(d)
            if not b:
                continue
            ba = b.get("by_agent") or {}
            if isinstance(ba, defaultdict):
                ba = {k: {"in": v["in"], "out": v["out"]} for k, v in ba.items()}
            else:
                ba = {k: dict(v) if isinstance(v, dict) else v for k, v in ba.items()}
            daily_out.append(
                {
                    "day": d,
                    "spend_usd": round(float(b.get("spend_usd", 0)), 6),
                    "input_tokens": int(b.get("input_tokens", 0)),
                    "output_tokens": int(b.get("output_tokens", 0)),
                    "by_agent": ba,
                }
            )
        last_fb = dict(_last_fallback_run) if _last_fallback_run else None

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_bucket = None
    for row in daily_out:
        if row["day"] == today:
            today_bucket = row
            break

    with _lock:
        dq_runs = _dq_runs_total
        dq_warn = _dq_warning_total
        dq_last = dict(_dq_last) if _dq_last else None

    return {
        "fallback": {
            "total_events": _fallback_total,
            "by_agent": fb_by_agent,
            "last_run": last_fb,
        },
        "data_quality": {
            "runs_recorded": dq_runs,
            "warnings_total": dq_warn,
            "last_run": dq_last,
        },
        "errors": err_tail,
        "daily_spend": daily_out,
        "today_spend": today_bucket,
    }
