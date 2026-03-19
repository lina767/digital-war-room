"""
GEOINT / conflict events routes: heatmap and theater map data.
"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agents.config import DEFAULT_CONFLICT
from agents.geoint_agent import (
    get_conflict_events_for_heatmap,
    get_theater_events,
)

router = APIRouter()


@router.get("/conflict-events")
async def get_conflict_events(conflict: str = DEFAULT_CONFLICT, limit: int = 200):
    """
    GET /api/conflict-events?conflict=Iran&limit=200
    Returns conflict events with lat, lon, intensity for heatmap layer (ACLED).
    Requires ACLED_EMAIL + ACLED_PASSWORD (OAuth) or legacy ACLED_API_KEY. Intensity derived from fatalities and event type.
    """
    try:
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            lambda: get_conflict_events_for_heatmap(conflict, limit=max(50, min(500, limit))),
        )
        return {"events": events, "conflict": conflict}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/theater-events")
async def get_theater_events_route(conflict: str = DEFAULT_CONFLICT, limit: int = 400):
    """
    GET /api/theater-events?conflict=Iran&limit=400
    Returns unified theater map events: FIRMS thermal anomalies + ACLED (with lat/lon).
    Each event has lat, lon, event_type (airstrike | missile | drone | explosion | naval | fire | other), source, confidence, label.
    Use for Theater Map layer (e.g. Iran) with type-specific icons.
    """
    try:
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            lambda: get_theater_events(conflict, limit=max(100, min(600, limit))),
        )
        return {"events": events, "conflict": conflict}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
