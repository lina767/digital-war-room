from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


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
