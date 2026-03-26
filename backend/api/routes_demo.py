"""Demo snapshot endpoint backed by a real historical analysis run when available."""

import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import StateServiceDep
from middleware.tenant_context import get_request_ctx
from middleware.rate_limit import limiter
from services.demo_snapshot_export import export_demo_snapshot

router = APIRouter()

_DEMO_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "demo" / "demo_snapshot.json"


def _load_snapshot_from_disk() -> Any:
    """Read and parse the fallback demo payload from disk."""
    if not _DEMO_SNAPSHOT_PATH.is_file():
        return JSONResponse(
            status_code=503,
            content={"error": "demo_snapshot_unavailable"},
        )
    raw = _DEMO_SNAPSHOT_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def _iso_from_ts(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _historical_snapshot_from_state(state: StateServiceDep, request: Request) -> dict[str, Any] | None:
    """Use the most recent completed run from in-memory state as demo payload."""
    tenant_id = get_request_ctx(request).tenant_id
    runs = state.get_run_history(limit=50, tenant_id=tenant_id)
    for run in runs:
        conflict = str(run.get("conflict") or "").strip()
        if not conflict:
            continue
        if run.get("error"):
            continue
        cache_entry = state.get_cache(conflict, tenant_id=tenant_id)
        if not isinstance(cache_entry, dict):
            continue
        result = cache_entry.get("result")
        if not isinstance(result, dict):
            continue
        payload: dict[str, Any] = json.loads(json.dumps(result, default=str))
        run_iso = _iso_from_ts(run.get("at"))
        payload["_demo"] = True
        payload["snapshot_source"] = "historical_run"
        payload["scenario_id"] = f"historical-run-{payload.get('analysis_run_id') or int(run.get('at', 0) or 0)}"
        payload["scenario_title"] = f"Historical analysis run - {conflict}"
        payload["scenario_note"] = (
            f"Snapshot from a completed analysis run with real DQ scoring and _meta confidence"
            + (f" ({run_iso} UTC)." if run_iso else ".")
        )
        return payload
    return None


class DemoExportRequest(BaseModel):
    conflict: str = Field(default="Yemen", min_length=1, max_length=120)
    timeout_sec: int = Field(default=45, ge=5, le=300)
    base_url: str = Field(default="http://127.0.0.1:8000", min_length=8, max_length=200)


def _is_demo_export_authorized(secret_header: str | None) -> bool:
    expected = (os.getenv("DEMO_EXPORT_SECRET") or os.getenv("ANALYZE_TRIGGER_SECRET") or "").strip()
    if not expected:
        return False
    return secret_header == expected


def _demo_export_status() -> dict[str, Any]:
    if not _DEMO_SNAPSHOT_PATH.is_file():
        return {
            "exists": False,
            "path": str(_DEMO_SNAPSHOT_PATH),
            "last_modified_utc": None,
            "snapshot_source": None,
            "scenario_id": None,
            "agents_count": 0,
            "timeline_points": 0,
        }
    mtime_dt = datetime.fromtimestamp(_DEMO_SNAPSHOT_PATH.stat().st_mtime, tz=timezone.utc)
    mtime = mtime_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    age_hours = max(0.0, (datetime.now(timezone.utc) - mtime_dt).total_seconds() / 3600.0)
    payload = _load_snapshot_from_disk()
    if not isinstance(payload, dict):
        return {
            "exists": True,
            "path": str(_DEMO_SNAPSHOT_PATH),
            "last_modified_utc": mtime,
            "snapshot_source": None,
            "scenario_id": None,
            "agents_count": 0,
            "timeline_points": 0,
            "parse_error": True,
        }
    agents = payload.get("precomputed_agent_results")
    timeline = payload.get("score_timeline")
    agents_count = len(agents) if isinstance(agents, list) else 0
    timeline_points = len(timeline) if isinstance(timeline, list) else 0
    if age_hours <= 24 and agents_count >= 15 and timeline_points >= 8:
        health = "ok"
    elif age_hours <= 72 and agents_count >= 10 and timeline_points >= 4:
        health = "warn"
    else:
        health = "stale"
    return {
        "exists": True,
        "path": str(_DEMO_SNAPSHOT_PATH),
        "last_modified_utc": mtime,
        "age_hours": round(age_hours, 2),
        "health": health,
        "snapshot_source": payload.get("snapshot_source"),
        "scenario_id": payload.get("scenario_id"),
        "scenario_title": payload.get("scenario_title"),
        "conflict": payload.get("conflict"),
        "analysis_run_id": payload.get("analysis_run_id"),
        "agents_count": agents_count,
        "timeline_points": timeline_points,
    }


@router.get("/demo/snapshot")
@limiter.limit("120/minute")
async def get_demo_snapshot(request: Request, state: StateServiceDep) -> Any:
    """
    GET /api/demo/snapshot
    Returns a curated, versioned analysis JSON (e.g. Red Sea chokepoint scenario).
    """
    historical = _historical_snapshot_from_state(state, request)
    if historical is not None:
        return historical
    fallback = _load_snapshot_from_disk()
    if isinstance(fallback, dict):
        fallback["snapshot_source"] = "fallback_snapshot"
    return fallback


@router.get("/demo")
@limiter.limit("120/minute")
async def get_demo(request: Request, state: StateServiceDep) -> Any:
    """
    GET /api/demo
    Alias for /api/demo/snapshot so GTM demos can use a simpler URL.
    """
    historical = _historical_snapshot_from_state(state, request)
    if historical is not None:
        return historical
    fallback = _load_snapshot_from_disk()
    if isinstance(fallback, dict):
        fallback["snapshot_source"] = "fallback_snapshot"
    return fallback


@router.post("/demo/export")
@limiter.limit("5/minute")
async def post_demo_export(
    request: Request,
    body: DemoExportRequest,
    x_demo_export_secret: str | None = Header(default=None, alias="X-Demo-Export-Secret"),
) -> Any:
    """
    POST /api/demo/export
    Export sanitized demo_snapshot.json from latest cached analysis + timeline.
    """
    if not _is_demo_export_authorized(x_demo_export_secret):
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    try:
        res = export_demo_snapshot(
            conflict=body.conflict.strip(),
            timeout=body.timeout_sec,
            base_url=body.base_url.rstrip("/"),
        )
        return {
            "status": "ok",
            "conflict": body.conflict.strip(),
            "snapshot_source": "historical_run",
            **res,
        }
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"demo_export_failed: {e}"})


@router.get("/demo/export/status")
@limiter.limit("30/minute")
async def get_demo_export_status() -> Any:
    """
    GET /api/demo/export/status
    Returns metadata about the current demo snapshot file.
    """
    return _demo_export_status()
