"""
GreyNoise Emerging Threats API – serves pre-computed snapshots from SQLite.
No live GreyNoise API calls in the request path; data is refreshed by the 6h scheduler.
"""

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from agents.greynoise_agent import get_latest_ips, get_latest_snapshot, get_trend_data, run_greynoise_agent
from utils.sanitize import sanitize_conflict

router = APIRouter(prefix="/greynoise", tags=["greynoise"])


@router.get("/{conflict}")
async def greynoise_latest(conflict: str):
    """
    GET /api/greynoise/{conflict}
    Returns the latest GreyNoise snapshot for a conflict from SQLite.
    Falls back to a live pipeline run if no snapshot exists yet.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    snapshot = get_latest_snapshot(conflict)
    if snapshot:
        snapshot["top_ips"] = get_latest_ips(conflict, limit=30)
        return snapshot

    # No snapshot yet – run pipeline once (blocking, but only on first request)
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: run_greynoise_agent(conflict))
        result["top_ips"] = get_latest_ips(conflict, limit=30)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "conflict": conflict})


@router.get("/{conflict}/trend")
async def greynoise_trend(conflict: str, days: int = Query(default=7, ge=1, le=90)):
    """
    GET /api/greynoise/{conflict}/trend?days=7
    Returns a time series of GreyNoise scores for the past N days.
    """
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    data = get_trend_data(conflict, days=days)
    return {"conflict": conflict, "days": days, "trend": data}
