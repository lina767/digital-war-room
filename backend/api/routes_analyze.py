"""
Analyze and agents state routes: stream, status, latest, timeline, refresh, trigger.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from agents.config import DEFAULT_CONFLICT
from agents.supervisor import analyze_conflict, run_analysis_streaming
from models.analysis import AnalysisResult

from .state_helpers import (
    get_cache,
    get_escalation_timeline,
    get_last_error,
    get_state_service,
    push_agent_status,
    push_escalation_timeline,
    push_run_history,
)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


# Max wall-clock time for a single analysis run (e.g. OFAC + 11 agents + LLM).
ANALYZE_TIMEOUT_SEC = 300  # 5 minutes


@router.get("/analyze/stream")
async def analyze_stream(request: Request, conflict: str = DEFAULT_CONFLICT) -> StreamingResponse:
    """
    GET /api/analyze/stream?conflict=Iran
    Server-Sent Events: one event per agent as it completes, then a final supervisor event.
    Event data: {"event": "agent", "agent": "finint", "result": {...}} or {"event": "supervisor", "result": {...}}.
    """

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
async def agents_status(request: Request) -> Any:
    """
    GET /api/agents/status
    Per-agent status from last completed analysis. Returns rich object per agent when _meta was present:
    status, fetched_at, duration_ms, confidence, data_freshness, sources, fallback_used, error_summary.
    """
    state = get_state_service(request)
    if state:
        return state.get_agent_status()
    status = getattr(request.app.state, "agent_status_last", None)
    return dict(status) if status else {}


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
async def agents_history(request: Request, limit: int = 20) -> Any:
    """
    GET /api/agents/history?limit=20
    Last N analysis run summaries: timestamp, conflict, per-agent duration, overall score, errors.
    """
    state = get_state_service(request)
    if state:
        runs = state.get_run_history(limit=limit)
        return {"runs": runs}
    history = getattr(request.app.state, "analysis_run_history", None)
    if history is None:
        return {"runs": []}
    runs = list(history)[-limit:]
    runs.reverse()
    return {"runs": runs}


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = DEFAULT_CONFLICT) -> Any:
    """
    GET /analyze/status?conflict=Iran
    Leichtgewichtige Antwort: ob Cache existiert, wann zuletzt aktualisiert,
    und ob die letzte Background-Analyse fehlgeschlagen ist (error).
    """
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
async def analyze(request: Request, body: AnalyzeRequest) -> Any:
    """
    POST /analyze – startet KEINE neue Analyse.
    Gibt nur die gecachte Analyse zurück (wie GET /analyze/latest).
    Analysen laufen stündlich im Hintergrund.
    """
    entry = get_cache(request, body.conflict)
    if not entry:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No cached analysis yet. Analysis runs automatically every 6 hours.",
                "conflict": body.conflict,
            },
        )
    return AnalysisResult.model_validate(entry["result"])


@router.get("/analyze/refresh")
async def refresh_analysis(request: Request, conflict: str = DEFAULT_CONFLICT, sync: bool = False) -> Any:
    """
    GET /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    On failure, error is stored and returned via GET /analyze/status.
    """
    app_state = request.app.state
    state = get_state_service(request)
    if state:
        state.pop_last_error(conflict)
    else:
        le = getattr(app_state, "analysis_last_error", None)
        if le is not None:
            le.pop(conflict, None)

    if sync:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            if state:
                state.set_cache(conflict, result, at_ts)
            else:
                app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            ws_manager = getattr(app_state, "ws_manager", None)
            if ws_manager:
                await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            return {"status": "ok", "conflict": conflict}
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            if state:
                state.set_last_error(conflict, msg)
            else:
                le = getattr(app_state, "analysis_last_error", None)
                if le is not None:
                    le[conflict] = msg
            return JSONResponse(status_code=504, content={"error": msg, "conflict": conflict})
        except Exception as e:
            import traceback

            if state:
                state.set_last_error(conflict, str(e))
            else:
                le = getattr(app_state, "analysis_last_error", None)
                if le is not None:
                    le[conflict] = str(e)
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})

    async def _run_in_background() -> None:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            if state:
                state.set_cache(conflict, result, at_ts)
            else:
                app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            if state:
                state.pop_last_error(conflict)
            else:
                getattr(app_state, "analysis_last_error", {}).pop(conflict, None)
            ws_manager = getattr(app_state, "ws_manager", None)
            if ws_manager:
                await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            print(f"[refresh] Analysis for {conflict} done and cached.")
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            if state:
                state.set_last_error(conflict, msg)
            else:
                le = getattr(app_state, "analysis_last_error", None)
                if le is not None:
                    le[conflict] = msg
            print(f"[refresh] Analysis for {conflict} failed: {msg}")
        except Exception as e:
            if state:
                state.set_last_error(conflict, str(e))
            else:
                le = getattr(app_state, "analysis_last_error", None)
                if le is not None:
                    le[conflict] = str(e)
            print(f"[refresh] Analysis for {conflict} failed: {e}")

    asyncio.create_task(_run_in_background())
    return {
        "status": "started",
        "conflict": conflict,
        "message": "Analysis running in background. Poll /api/analyze/status to check.",
    }


@router.post("/analyze/trigger")
async def trigger_analysis(
    request: Request,
    conflict: str = DEFAULT_CONFLICT,
    x_trigger_secret: str | None = Header(default=None, alias="X-Trigger-Secret"),
) -> Any:
    """
    Führt einmalig eine Analyse aus und füllt den Cache (z. B. nach Neustart oder Limit-Reset).
    Optional: ANALYZE_TRIGGER_SECRET in Railway setzen, dann Header X-Trigger-Secret mitschicken.
    """
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
        state = get_state_service(request)
        if state:
            state.set_cache(conflict, result, at_ts)
        else:
            request.app.state.analysis_cache[conflict] = {"result": result, "at": at_ts}
        push_escalation_timeline(request.app.state, conflict, at_ts, result)
        push_agent_status(request.app.state, result)
        push_run_history(request.app.state, conflict, at_ts, result)
        ws_manager = getattr(request.app.state, "ws_manager", None)
        if ws_manager:
            await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
        return AnalysisResult.model_validate(result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
