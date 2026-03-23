"""Public curated demo snapshot (no live agent spend for demo traffic)."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from middleware.rate_limit import limiter

router = APIRouter()

_DEMO_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "demo" / "demo_snapshot.json"


@router.get("/demo/snapshot")
@limiter.limit("120/minute")
async def get_demo_snapshot(request: Request) -> Any:
    """
    GET /api/demo/snapshot
    Returns a curated, versioned analysis JSON (e.g. Red Sea chokepoint scenario).
    """
    if not _DEMO_SNAPSHOT_PATH.is_file():
        return JSONResponse(
            status_code=503,
            content={"error": "demo_snapshot_unavailable"},
        )
    raw = _DEMO_SNAPSHOT_PATH.read_text(encoding="utf-8")
    return json.loads(raw)
