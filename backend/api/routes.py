import os
import asyncio
import time

from fastapi import APIRouter, Request, Header
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from agents.supervisor import analyze_conflict

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = "US-Iran"):
    """
    GET /analyze/status?conflict=US-Iran
    Leichtgewichtige Antwort: ob Cache existiert und wann zuletzt aktualisiert.
    Hilft dem Frontend zu unterscheiden: Backend down vs. noch keine Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return {"cached": False, "conflict": conflict}
    return {"cached": True, "conflict": conflict, "at": entry.get("at")}


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = "US-Iran"):
    """
    GET /analyze/latest?conflict=US-Iran
    Liefert die letzte gecachte Analyse (nur vom 10-Min-Auto-Run). Startet keine neue Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return Response(status_code=404)
    return entry["result"]


@router.post("/analyze")
async def analyze(request: Request, body: AnalyzeRequest):
    """
    POST /analyze – startet KEINE neue Analyse.
    Gibt nur die gecachte Analyse zurück (wie GET /analyze/latest).
    Analysen laufen ausschließlich alle 10 Minuten im Hintergrund.
    """
    cache = _get_cache(request)
    entry = cache.get(body.conflict)
    if not entry:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No cached analysis yet. Analysis runs automatically every 10 minutes.",
                "conflict": body.conflict,
            },
        )
    return entry["result"]


@router.post("/analyze/trigger")
async def trigger_analysis(
    request: Request,
    conflict: str = "US-Iran",
    x_trigger_secret: str | None = Header(default=None, alias="X-Trigger-Secret"),
):
    """
    Führt einmalig eine Analyse aus und füllt den Cache (z. B. nach Neustart oder Limit-Reset).
    Optional: ANALYZE_TRIGGER_SECRET in Railway setzen, dann Header X-Trigger-Secret mitschicken.
    """
    secret = os.getenv("ANALYZE_TRIGGER_SECRET", "").strip()
    if secret and x_trigger_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Trigger-Secret"})
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: analyze_conflict(conflict))
        cache = _get_cache(request)
        cache[conflict] = {"result": result, "at": time.time()}
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
