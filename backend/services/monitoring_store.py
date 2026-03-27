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

# Research enrichment aggregates (process lifetime)
_research_cases_total = 0
_research_triggered_total = 0
_research_conflict_cases = 0
_research_auto_publish_total = 0
_research_human_review_total = 0
_research_cost_total_usd = 0.0
_research_required_before_filled = 0
_research_required_before_total = 0
_research_required_after_filled = 0
_research_required_after_total = 0
_research_last_run: Optional[Dict[str, Any]] = None

# Last Google web SERP snapshot from monitoring (POST /agents/google-trend-snapshot); process lifetime
_google_trend_serp: Optional[Dict[str, Any]] = None

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
    try:
        _record_research_from_analysis(conflict, result)
    except Exception:
        pass


def _record_research_from_analysis(conflict: str, result: Dict[str, Any]) -> None:
    global _research_cases_total, _research_triggered_total, _research_conflict_cases
    global _research_auto_publish_total, _research_human_review_total, _research_cost_total_usd
    global _research_required_before_filled, _research_required_before_total
    global _research_required_after_filled, _research_required_after_total
    global _research_last_run
    research = result.get("research_enrichment")
    if not isinstance(research, dict):
        return

    triggered = bool(research.get("triggered"))
    publish_decision = str(research.get("publish_decision") or result.get("review_decision") or "").strip().lower()
    reasons = research.get("trigger_decision", {}).get("reasons") if isinstance(research.get("trigger_decision"), dict) else []
    has_agent_conflict_reason = False
    if isinstance(reasons, list):
        for r in reasons:
            if isinstance(r, dict) and str(r.get("trigger")) == "agent_conflict":
                has_agent_conflict_reason = True
                break
    usage = (research.get("budget_status") or {}).get("usage")
    cost = 0.0
    if isinstance(usage, dict):
        try:
            cost = float(usage.get("estimated_cost_usd") or 0.0)
        except Exception:
            cost = 0.0
    before = research.get("required_field_coverage_before") if isinstance(research.get("required_field_coverage_before"), dict) else {}
    after = research.get("required_field_coverage_after") if isinstance(research.get("required_field_coverage_after"), dict) else {}
    try:
        before_filled = int(before.get("filled_required_fields") or 0)
        before_total = int(before.get("total_required_fields") or 0)
        after_filled = int(after.get("filled_required_fields") or 0)
        after_total = int(after.get("total_required_fields") or 0)
    except Exception:
        before_filled = before_total = after_filled = after_total = 0

    with _lock:
        _research_cases_total += 1
        if triggered:
            _research_triggered_total += 1
        if has_agent_conflict_reason:
            _research_conflict_cases += 1
        if publish_decision == "human_review":
            _research_human_review_total += 1
        else:
            _research_auto_publish_total += 1
        _research_cost_total_usd += max(0.0, cost)
        _research_required_before_filled += max(0, before_filled)
        _research_required_before_total += max(0, before_total)
        _research_required_after_filled += max(0, after_filled)
        _research_required_after_total += max(0, after_total)
        _research_last_run = {
            "conflict": conflict,
            "at": time.time(),
            "triggered": triggered,
            "publish_decision": publish_decision or "auto_publish",
            "analysis_en": str(research.get("analysis_en") or "").strip(),
            "air_activity_assessment_en": str(research.get("air_activity_assessment_en") or "").strip(),
            "findings": [str(x) for x in (research.get("findings") or [])[:6] if isinstance(x, str)],
        }


def set_google_trend_serp(payload: Optional[Dict[str, Any]]) -> None:
    """Store last Google trend SerpAPI snapshot (success or error payload) for Agent Monitor."""
    global _google_trend_serp
    with _lock:
        _google_trend_serp = dict(payload) if isinstance(payload, dict) else None


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
        gts = dict(_google_trend_serp) if _google_trend_serp else None
        r_cases = _research_cases_total
        r_triggered = _research_triggered_total
        r_conflicts = _research_conflict_cases
        r_auto = _research_auto_publish_total
        r_review = _research_human_review_total
        r_cost = _research_cost_total_usd
        rb_filled = _research_required_before_filled
        rb_total = _research_required_before_total
        ra_filled = _research_required_after_filled
        ra_total = _research_required_after_total
        r_last = dict(_research_last_run) if isinstance(_research_last_run, dict) else None

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
        "google_trend_serp": gts,
        "research": {
            "cases_total": r_cases,
            "triggered_total": r_triggered,
            "conflict_cases": r_conflicts,
            "auto_publish_total": r_auto,
            "human_review_total": r_review,
            "total_cost_usd": round(float(r_cost), 8),
            "cost_per_case_usd": round(float(r_cost / r_cases), 8) if r_cases > 0 else 0.0,
            "required_fields_before": {"filled": rb_filled, "total": rb_total},
            "required_fields_after": {"filled": ra_filled, "total": ra_total},
            "last_run": r_last,
        },
    }
