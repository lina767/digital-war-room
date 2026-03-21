"""
Analyze and agents state routes: stream, status, latest, timeline, refresh, trigger.
Rate limiting and input sanitization applied to all conflict-bearing endpoints.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api.deps import StateServiceDep, WsManagerDep
from agents.config import DEFAULT_CONFLICT
from agents.supervisor import analyze_conflict, run_analysis_streaming
from middleware.rate_limit import limiter
from models.analysis import AnalysisResult
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
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})

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


@router.get("/agents/status")
async def agents_status(state: StateServiceDep) -> Any:
    """
    GET /api/agents/status
    Per-agent status from last completed analysis. Returns rich object per agent when _meta was present:
    status, fetched_at, duration_ms, confidence, data_freshness, sources, fallback_used, error_summary.
    """
    return state.get_agent_status()


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


@router.get("/agents/history")
async def agents_history(state: StateServiceDep, limit: int = 20) -> Any:
    """
    GET /api/agents/history?limit=20
    Last N analysis run summaries: timestamp, conflict, per-agent duration, overall score, errors.
    """
    runs = state.get_run_history(limit=limit)
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
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    entry = get_cache(request, conflict)
    last_err = get_last_error(request, conflict)
    out = {"cached": bool(entry), "conflict": conflict}
    if entry:
        out["at"] = entry.get("at")
    if last_err:
        out["error"] = last_err
    return out


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /analyze/latest?conflict=Iran
    Liefert die letzte gecachte Analyse (nur vom 10-Min-Auto-Run). Startet keine neue Analyse.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
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
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
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
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
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


@router.get("/analyze/refresh")
@limiter.limit("10/minute")
async def refresh_analysis(
    request: Request,
    state: StateServiceDep,
    ws_manager: WsManagerDep,
    conflict: str = DEFAULT_CONFLICT,
    sync: bool = False,
) -> Any:
    """
    GET /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    On failure, error is stored and returned via GET /analyze/status.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    app_state = request.app.state
    state.pop_last_error(conflict)

    if sync:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            state.set_cache(conflict, result, at_ts)
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            return {"status": "ok", "conflict": conflict}
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            state.set_last_error(conflict, msg)
            return JSONResponse(status_code=504, content={"error": msg, "conflict": conflict})
        except Exception as e:
            import traceback

            state.set_last_error(conflict, str(e))
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})

    async def _run_in_background() -> None:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            state.set_cache(conflict, result, at_ts)
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            state.pop_last_error(conflict)
            await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            print(f"[refresh] Analysis for {conflict} done and cached.")
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            state.set_last_error(conflict, msg)
            print(f"[refresh] Analysis for {conflict} failed: {msg}")
        except Exception as e:
            state.set_last_error(conflict, str(e))
            print(f"[refresh] Analysis for {conflict} failed: {e}")

    asyncio.create_task(_run_in_background())
    return {
        "status": "started",
        "conflict": conflict,
        "message": "Analysis running in background. Poll /api/analyze/status to check.",
    }


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
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    secret = os.getenv("ANALYZE_TRIGGER_SECRET", "").strip()
    if secret and x_trigger_secret != secret:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Invalid or missing X-Trigger-Secret. Remove ANALYZE_TRIGGER_SECRET from env to disable."
            },
        )
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: analyze_conflict(conflict))
        at_ts = time.time()
        state.set_cache(conflict, result, at_ts)
        push_escalation_timeline(request.app.state, conflict, at_ts, result)
        push_agent_status(request.app.state, result)
        push_run_history(request.app.state, conflict, at_ts, result)
        await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
        return AnalysisResult.model_validate(result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
