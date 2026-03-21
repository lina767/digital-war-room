"""
GEOINT / conflict events routes: heatmap and theater map data.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agents.config import DEFAULT_CONFLICT
from agents.geoint_agent import (
    get_conflict_events_for_heatmap,
    get_theater_events,
)
from api.http_errors import conflict_bad_request
from utils.sanitize import sanitize_conflict

router = APIRouter()


async def _conflict_events_response(
    conflict: str,
    limit: int,
    fetch: Callable[[str, int], Any],
    cap_lo: int,
    cap_hi: int,
) -> Any:
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return conflict_bad_request(e)
    try:
        loop = asyncio.get_running_loop()
        bounded = max(cap_lo, min(cap_hi, limit))
        events = await loop.run_in_executor(None, lambda: fetch(conflict, limit=bounded))
        return {"events": events, "conflict": conflict}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/conflict-events")
async def get_conflict_events(conflict: str = DEFAULT_CONFLICT, limit: int = 200):
    """
    GET /api/conflict-events?conflict=Iran&limit=200
    Returns conflict events with lat, lon, intensity for heatmap layer (ACLED).
    Requires ACLED_EMAIL + ACLED_PASSWORD (OAuth) or legacy ACLED_API_KEY. Intensity derived from fatalities and event type.
    """
    return await _conflict_events_response(
        conflict, limit, get_conflict_events_for_heatmap, cap_lo=50, cap_hi=500
    )


@router.get("/theater-events")
async def get_theater_events_route(conflict: str = DEFAULT_CONFLICT, limit: int = 400):
    """
    GET /api/theater-events?conflict=Iran&limit=400
    Returns unified theater map events: FIRMS thermal anomalies + ACLED (with lat/lon).
    Each event has lat, lon, event_type (airstrike | missile | drone | explosion | naval | fire | other), source, confidence, label.
    Use for Theater Map layer (e.g. Iran) with type-specific icons.
    """
    return await _conflict_events_response(conflict, limit, get_theater_events, cap_lo=100, cap_hi=600)
