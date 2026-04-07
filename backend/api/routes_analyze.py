"""
Analyze and agents state routes: stream, status, latest, timeline, refresh, trigger.
Rate limiting and input sanitization applied to all conflict-bearing endpoints.
"""

import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from middleware.tenant_context import get_request_ctx
from api.deps import StateServiceDep, WsManagerDep
from api.http_errors import conflict_bad_request
from agents.config import DEFAULT_CONFLICT
from agents.pattern_anomalies import attach_pattern_flags
from agents.supervisor import analyze_conflict, run_analysis_streaming
from middleware.rate_limit import limiter
from models.analysis import AnalysisResult
from services.analysis_side_effects import persist_analysis_side_effects
from services.tenant_constants import get_default_tenant_id
from utils.sanitize import CONFLICT_MAX_LEN, sanitize_conflict

from .state_helpers import (
    get_cache,
    get_escalation_timeline,
    get_last_error,
    push_agent_status,
    push_escalation_timeline,
    push_run_history,
)

router = APIRouter()
logger = logging.getLogger(__name__)
REFRESH_DEPRECATION_HEADERS = {
    "Deprecation": "true",
    "Sunset": "Wed, 31 Dec 2026 23:59:59 GMT",
    "Link": '</api/analyze/refresh>; rel="successor-version"; title="Use POST /api/analyze/refresh"',
}


def _run_analyze_in_context(ctx: Any, conflict: str) -> Any:
    """Run sync analyze_conflict with RequestContext (needed for executor threads)."""
    from services.request_context import reset_request_context, set_request_context

    token = set_request_context(ctx)
    try:
        return analyze_conflict(conflict)
    finally:
        reset_request_context(token)


async def _persist_analysis_result(
    *,
    conflict: str,
    result: dict[str, Any],
    state: StateServiceDep,
    app_state: Any,
    ws_manager: WsManagerDep,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Write analysis to cache, timeline, agent status, run history; broadcast to WebSocket clients."""
    at_ts = time.time()
    attach_pattern_flags(state, conflict, result, tenant_id=tenant_id)
    state.set_cache(conflict, result, at_ts, tenant_id=tenant_id)
    push_escalation_timeline(app_state, conflict, at_ts, result, tenant_id=tenant_id)
    push_agent_status(app_state, result, tenant_id=tenant_id)
    push_run_history(app_state, conflict, at_ts, result, tenant_id=tenant_id)
    await ws_manager.broadcast(
        {**result, "status": "ok", "conflict": conflict},
        conflict=conflict,
        tenant_id=tenant_id or get_default_tenant_id(),
    )
    await persist_analysis_side_effects(conflict, result, tenant_id=tenant_id)


class AnalyzeRequest(BaseModel):
    conflict: str = Field(..., min_length=1, max_length=CONFLICT_MAX_LEN, description="Conflict identifier")

    @field_validator("conflict", mode="before")
    @classmethod
    def _strip_conflict(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("conflict must be a string")
        return v.strip()

    @field_validator("conflict")
    @classmethod
    def _validate_conflict(cls, v: str) -> str:
        return sanitize_conflict(v)


# Max wall-clock time for a single analysis run (e.g. OFAC + 11 agents + LLM).
ANALYZE_TIMEOUT_SEC = 300  # 5 minutes


def _inflight_key(conflict: str, tenant_id: uuid.UUID | None) -> str:
    return f"{tenant_id or 'default'}\n{conflict}"


def _ensure_inflight_registry(app_state: Any) -> dict[str, float]:
    registry = getattr(app_state, "analysis_inflight", None)
    if isinstance(registry, dict):
        return registry
    registry = {}
    setattr(app_state, "analysis_inflight", registry)
    return registry


def _try_mark_inflight(app_state: Any, key: str) -> bool:
    registry = _ensure_inflight_registry(app_state)
    if key in registry:
        return False
    registry[key] = time.time()
    return True


def _clear_inflight(app_state: Any, key: str) -> None:
    _ensure_inflight_registry(app_state).pop(key, None)


def _with_refresh_deprecation_headers(result: Any) -> Response:
    if isinstance(result, Response):
        for k, v in REFRESH_DEPRECATION_HEADERS.items():
            result.headers[k] = v
        return result
    return JSONResponse(content=result, headers=REFRESH_DEPRECATION_HEADERS)


@router.get("/analyze/stream")
@limiter.limit("10/minute")
async def analyze_stream(request: Request, conflict: str = DEFAULT_CONFLICT) -> StreamingResponse:
    """
    GET /api/analyze/stream?conflict=Iran
    Server-Sent Events: one event per agent as it completes, then a final supervisor event.
    Event data: {"event": "agent", "agent": "finint", "result": {...}} or {"event": "supervisor", "result": {...}}.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)

    async def event_stream() -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_stream() -> None:
            try:
                for name, data in run_analysis_streaming(conflict):
                    loop.call_soon_threadsafe(queue.put_nowait, (name, data))
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
            loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, run_stream)
        while True:
            item = await queue.get()
            if item is None:
                break
            if item[0] == "error":
                yield f"data: {json.dumps({'event': 'error', 'message': item[1]}, default=str)}\n\n"
                break
            name, data = item
            if name == "supervisor":
                yield f"data: {json.dumps({'event': 'supervisor', 'result': data}, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'event': 'agent', 'agent': name, 'result': data}, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status")
async def agents_ops_status() -> Any:
    """
    GET /api/status
    Ops snapshot for monitoring: per-agent heartbeat (last run, last successful run, 24h error rate,
    Haiku token slice), plus global Anthropic budget. In-memory since process start; structured
    ``agent_heartbeat`` logs are also emitted on each agent node completion.
    """
    from services.agent_heartbeat_store import get_ops_snapshot

    return get_ops_snapshot()


@router.get("/agents/status")
async def agents_status(request: Request, state: StateServiceDep) -> Any:
    """
    GET /api/agents/status
    Per-agent status from last completed analysis. Returns rich object per agent when _meta was present:
    status, fetched_at, duration_ms, confidence, data_freshness, sources, fallback_used, error_summary.
    """
    return state.get_agent_status(tenant_id=get_request_ctx(request).tenant_id)


@router.get("/agents/health")
async def agents_health() -> Any:
    """
    GET /api/agents/health
    Per-source health report from HealthRegistry: availability %, avg latency, circuit_open, last_error.
    """
    from agents.health_registry import get_health_registry

    reg = get_health_registry()
    if reg is None:
        return {"sources": [], "summary": {"total_sources": 0, "degraded": 0, "down": 0, "ok": 0}}
    return reg.get_health_report()


@router.get("/agents/monitoring")
async def agents_monitoring() -> Any:
    """
    GET /api/agents/monitoring
    Fallback usage totals, recent error log (with optional detail), Haiku token/cost metrics,
    per-day spend rollups (in-memory, process lifetime), and optional cached Google SERP snapshot.
    """
    from services.haiku_service import get_haiku_metrics_for_api
    from services.monitoring_store import get_snapshot

    snap = get_snapshot()
    haiku = get_haiku_metrics_for_api()
    return {
        "fallback": snap["fallback"],
        "errors": snap["errors"],
        "research": snap.get("research"),
        "cost": {
            **haiku,
            "daily": snap["daily_spend"],
            "today": snap["today_spend"],
        },
        "google_trend_serp": snap.get("google_trend_serp"),
    }


@router.post("/agents/google-trend-snapshot")
async def agents_google_trend_snapshot(body: AnalyzeRequest) -> Any:
    """
    POST /api/agents/google-trend-snapshot
    One SerpAPI Google web search for the conflict's ranking query (see RANKING_QUERY_* / hf_service).
    Hard-capped via MONITORING_GOOGLE_SERPAPI_HOURLY_CAP and MONITORING_GOOGLE_SERPAPI_MONTHLY_CAP (separate file from Pentagon).
    Requires SERPAPI_KEY. Updates cached payload returned by GET /api/agents/monitoring.
    """
    from services.google_trend_serp import fetch_google_trend_snapshot
    from services.hf_service import _get_ranking_query
    from services.monitoring_store import set_google_trend_serp

    query = _get_ranking_query(body.conflict)
    result = await fetch_google_trend_snapshot(conflict=body.conflict, query=query)
    set_google_trend_serp(result)
    return result


@router.get("/agents/history")
async def agents_history(request: Request, state: StateServiceDep, limit: int = 20) -> Any:
    """
    GET /api/agents/history?limit=20
    Last N analysis run summaries: timestamp, conflict, per-agent duration, overall score, errors.
    """
    runs = state.get_run_history(limit=limit, tenant_id=get_request_ctx(request).tenant_id)
    return {"runs": runs}


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /analyze/status?conflict=Iran
    Leichtgewichtige Antwort: ob Cache existiert, wann zuletzt aktualisiert,
    und ob die letzte Background-Analyse fehlgeschlagen ist (error).
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    entry = get_cache(request, conflict)
    last_err = get_last_error(request, conflict)
    req_ctx = get_request_ctx(request)
    run_key = _inflight_key(conflict, req_ctx.tenant_id)
    inflight = _ensure_inflight_registry(request.app.state)
    out = {"cached": bool(entry), "conflict": conflict}
    out["running"] = run_key in inflight
    if entry:
        out["at"] = entry.get("at")
    if last_err:
        out["error"] = last_err
    return out


@router.get("/analyze/audit/{run_id}")
async def get_analysis_audit(run_id: str) -> Any:
    """
    GET /api/analyze/audit/{run_id}
    Returns stored provenance snapshot for a completed analysis run (requires DATABASE_URL).
    """
    try:
        uuid.UUID(run_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "invalid_run_id"})
    from services.analysis_audit_store import fetch_analysis_audit

    row = await fetch_analysis_audit(run_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "not_found", "run_id": run_id})
    return row


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /analyze/latest?conflict=Iran
    Liefert die letzte gecachte Analyse (nur vom 10-Min-Auto-Run). Startet keine neue Analyse.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    entry = get_cache(request, conflict)
    if not entry:
        return JSONResponse(status_code=404, content={"error": "no_cached_analysis", "conflict": conflict})
    return AnalysisResult.model_validate(entry["result"])


@router.get("/analyze/timeline")
async def get_escalation_timeline_route(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /analyze/timeline?conflict=Iran
    Returns escalation score over time for the Escalation Timeline UI.
    Each point is one completed analysis run (at, escalation_score). Points sorted by time ascending.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    raw = list(get_escalation_timeline(request, conflict) or [])
    points = []
    for p in raw:
        at_ts = p.get("at")
        score = p.get("escalation_score")
        try:
            dt = datetime.fromtimestamp(float(at_ts), tz=timezone.utc)
            points.append(
                {
                    "at": at_ts,
                    "escalation_score": score,
                    "datetime_iso": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "hour": dt.strftime("%H"),
                    "label": dt.strftime("%H:%M"),
                    "label_with_date": dt.strftime("%d.%m. %H:%M"),
                }
            )
        except (TypeError, ValueError, OSError):
            points.append(
                {"at": at_ts, "escalation_score": score, "datetime_iso": "", "label": "", "label_with_date": ""}
            )
    points.sort(key=lambda x: x.get("at") or 0)
    return {"conflict": conflict, "points": points}


@router.get("/analyze/snapshots")
async def get_agent_snapshots_runs(request: Request, conflict: str = DEFAULT_CONFLICT, limit: int = 20) -> Any:
    """
    GET /api/analyze/snapshots?conflict=Iran&limit=20
    Returns recent analysis runs persisted in Layer 3 (agent_snapshots).
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    from services.agent_snapshot_store import list_recent_runs

    runs = list_recent_runs(conflict=conflict, tenant_id=get_request_ctx(request).tenant_id, limit=limit)
    return {"conflict": conflict, "runs": runs}


@router.get("/analyze/diff")
async def analyze_diff(
    request: Request,
    conflict: str = DEFAULT_CONFLICT,
    run_id_prev: str | None = None,
    run_id_curr: str | None = None,
) -> Any:
    """
    GET /api/analyze/diff?conflict=Iran&run_id_prev=<uuid>&run_id_curr=<uuid>
    Deterministic structured diff between two Layer 3 runs.
    If run ids are omitted, picks latest two runs for the conflict.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)

    from services.diff_engine import auto_pick_runs_for_diff, diff_runs

    tid = get_request_ctx(request).tenant_id
    if not run_id_prev or not run_id_curr:
        picked = auto_pick_runs_for_diff(conflict=conflict, tenant_id=tid)
        if not picked:
            return JSONResponse(
                status_code=404,
                content={"error": "insufficient_runs", "conflict": conflict, "message": "Need at least two persisted runs."},
            )
        run_id_prev = picked["run_id_prev"]
        run_id_curr = picked["run_id_curr"]

    try:
        uuid.UUID(str(run_id_prev))
        uuid.UUID(str(run_id_curr))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid_run_id"})

    out = diff_runs(
        conflict=conflict,
        run_id_prev=str(run_id_prev),
        run_id_curr=str(run_id_curr),
        tenant_id=tid,
    )
    if out.get("error"):
        return JSONResponse(status_code=404, content=out)
    return out


@router.get("/analyze/daily-snapshot")
async def get_daily_snapshot(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /api/analyze/daily-snapshot?conflict=Iran
    Returns latest Layer 5 daily materialized snapshot for this conflict.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)

    from services.daily_snapshot_store import get_latest_daily_snapshot

    row = get_latest_daily_snapshot(conflict=conflict, tenant_id=get_request_ctx(request).tenant_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "not_found", "conflict": conflict})
    return {"conflict": conflict, "snapshot": row}


@router.post("/analyze/daily-snapshot/materialize")
@limiter.limit("10/minute")
async def materialize_daily_snapshot_route(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    POST /api/analyze/daily-snapshot/materialize?conflict=Iran
    Builds Layer 5 snapshot from latest Layer 3 + Layer 4 data.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)

    from services.daily_snapshot_job import materialize_daily_snapshot

    out = materialize_daily_snapshot(conflict=conflict, tenant_id=get_request_ctx(request).tenant_id)
    if out.get("status") != "ok":
        return JSONResponse(status_code=404, content=out)
    return out


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze(request: Request, body: AnalyzeRequest) -> Any:
    """
    POST /analyze – startet KEINE neue Analyse.
    Gibt nur die gecachte Analyse zurück (wie GET /analyze/latest).
    Analysen laufen stündlich im Hintergrund.
    """
    try:
        conflict = sanitize_conflict(body.conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    entry = get_cache(request, conflict)
    if not entry:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No cached analysis yet. Analysis runs automatically every 6 hours.",
                "conflict": conflict,
            },
        )
    return AnalysisResult.model_validate(entry["result"])


async def _refresh_analysis_impl(
    request: Request,
    state: StateServiceDep,
    ws_manager: WsManagerDep,
    conflict: str = DEFAULT_CONFLICT,
    sync: bool = False,
) -> Any:
    """
    /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    On failure, error is stored and returned via GET /analyze/status.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    app_state = request.app.state
    req_ctx = get_request_ctx(request)
    tid = req_ctx.tenant_id
    run_key = _inflight_key(conflict, tid)
    state.pop_last_error(conflict, tenant_id=tid)

    if sync:
        if not _try_mark_inflight(app_state, run_key):
            return JSONResponse(
                status_code=409,
                content={"status": "already_running", "conflict": conflict, "message": "Analysis is already running."},
            )
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _run_analyze_in_context(req_ctx, conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            await _persist_analysis_result(
                conflict=conflict,
                result=result,
                state=state,
                app_state=app_state,
                ws_manager=ws_manager,
                tenant_id=tid,
            )
            return {"status": "ok", "conflict": conflict}
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            state.set_last_error(conflict, msg, tenant_id=tid)
            return JSONResponse(status_code=504, content={"error": msg, "conflict": conflict})
        except Exception as e:
            state.set_last_error(conflict, str(e), tenant_id=tid)
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})
        finally:
            _clear_inflight(app_state, run_key)

    if not _try_mark_inflight(app_state, run_key):
        return {
            "status": "already_running",
            "conflict": conflict,
            "message": "Analysis already running. Poll /api/analyze/status to check.",
        }

    async def _run_in_background() -> None:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _run_analyze_in_context(req_ctx, conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            state.pop_last_error(conflict, tenant_id=tid)
            await _persist_analysis_result(
                conflict=conflict,
                result=result,
                state=state,
                app_state=app_state,
                ws_manager=ws_manager,
                tenant_id=tid,
            )
            logger.info("Analysis refresh completed and cached for conflict=%s", conflict)
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            state.set_last_error(conflict, msg, tenant_id=tid)
            logger.warning("Analysis refresh failed for conflict=%s: %s", conflict, msg)
        except Exception as e:
            state.set_last_error(conflict, str(e), tenant_id=tid)
            logger.warning("Analysis refresh failed for conflict=%s: %s", conflict, e)
        finally:
            _clear_inflight(app_state, run_key)

    asyncio.create_task(_run_in_background())
    return {
        "status": "started",
        "conflict": conflict,
        "message": "Analysis running in background. Poll /api/analyze/status to check.",
    }


@router.post("/analyze/refresh")
@limiter.limit("10/minute")
async def refresh_analysis(
    request: Request,
    state: StateServiceDep,
    ws_manager: WsManagerDep,
    conflict: str = DEFAULT_CONFLICT,
    sync: bool = False,
) -> Any:
    """
    POST /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    On failure, error is stored and returned via GET /api/analyze/status.
    """
    return await _refresh_analysis_impl(
        request=request,
        state=state,
        ws_manager=ws_manager,
        conflict=conflict,
        sync=sync,
    )


@router.get("/analyze/refresh")
@limiter.limit("10/minute")
async def refresh_analysis_legacy_get(
    request: Request,
    state: StateServiceDep,
    ws_manager: WsManagerDep,
    conflict: str = DEFAULT_CONFLICT,
    sync: bool = False,
) -> Any:
    """
    Legacy GET alias for /analyze/refresh.
    Prefer POST for side-effecting trigger requests.
    """
    logger.warning("Deprecated GET /api/analyze/refresh called; prefer POST.")
    result = await _refresh_analysis_impl(
        request=request,
        state=state,
        ws_manager=ws_manager,
        conflict=conflict,
        sync=sync,
    )
    return _with_refresh_deprecation_headers(result)


@router.post("/analyze/trigger")
@limiter.limit("5/minute")
async def trigger_analysis(
    request: Request,
    state: StateServiceDep,
    ws_manager: WsManagerDep,
    conflict: str = DEFAULT_CONFLICT,
    x_trigger_secret: str | None = Header(default=None, alias="X-Trigger-Secret"),
) -> Any:
    """
    Führt einmalig eine Analyse aus und füllt den Cache (z. B. nach Neustart oder Limit-Reset).
    Optional: ANALYZE_TRIGGER_SECRET in Railway setzen, dann Header X-Trigger-Secret mitschicken.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    secret = os.getenv("ANALYZE_TRIGGER_SECRET", "").strip()
    if secret and x_trigger_secret != secret:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Invalid or missing X-Trigger-Secret. Remove ANALYZE_TRIGGER_SECRET from env to disable."
            },
        )
    req_ctx = get_request_ctx(request)
    run_key = _inflight_key(conflict, req_ctx.tenant_id)
    if not _try_mark_inflight(request.app.state, run_key):
        return JSONResponse(
            status_code=409,
            content={"status": "already_running", "conflict": conflict, "message": "Analysis is already running."},
        )
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _run_analyze_in_context(req_ctx, conflict)),
            timeout=float(ANALYZE_TIMEOUT_SEC),
        )
        await _persist_analysis_result(
            conflict=conflict,
            result=result,
            state=state,
            app_state=request.app.state,
            ws_manager=ws_manager,
            tenant_id=req_ctx.tenant_id,
        )
        return AnalysisResult.model_validate(result)
    except asyncio.TimeoutError:
        msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
        state.set_last_error(conflict, msg, tenant_id=req_ctx.tenant_id)
        return JSONResponse(status_code=504, content={"error": msg, "conflict": conflict})
    except Exception as e:
        state.set_last_error(conflict, str(e), tenant_id=req_ctx.tenant_id)
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        _clear_inflight(request.app.state, run_key)
