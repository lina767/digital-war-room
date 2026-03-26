"""Demo snapshot endpoint backed by a real historical analysis run when available."""

import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.deps import StateServiceDep
from middleware.tenant_context import get_request_ctx
from middleware.rate_limit import limiter

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
        payload["scenario_id"] = f"historical-run-{payload.get('analysis_run_id') or int(run.get('at', 0) or 0)}"
        payload["scenario_title"] = f"Historical analysis run - {conflict}"
        payload["scenario_note"] = (
            f"Snapshot from a completed analysis run with real DQ scoring and _meta confidence"
            + (f" ({run_iso} UTC)." if run_iso else ".")
        )
        return payload
    return None


@router.get("/demo/snapshot")
@limiter.limit("120/minute")
async def get_demo_snapshot(request: Request, state: StateServiceDep) -> Any:
    """
    GET /api/demo/snapshot
    Returns a curated, versioned analysis JSON (e.g. Red Sea chokepoint scenario).
    """
    return _historical_snapshot_from_state(state, request) or _load_snapshot_from_disk()


@router.get("/demo")
@limiter.limit("120/minute")
async def get_demo(request: Request, state: StateServiceDep) -> Any:
    """
    GET /api/demo
    Alias for /api/demo/snapshot so GTM demos can use a simpler URL.
    """
    return _historical_snapshot_from_state(state, request) or _load_snapshot_from_disk()
