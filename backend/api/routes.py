import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from agents.supervisor import analyze_conflict


router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = "US-Iran"):
    """
    GET /analyze/latest?conflict=US-Iran
    Returns the last cached analysis for that conflict (from auto-run or last POST).
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return Response(status_code=404)
    return entry["result"]


@router.post("/analyze")
async def analyze(request: Request, body: AnalyzeRequest):
    """
    POST /analyze
    Body: {"conflict": "US-Iran"}
    Returns the full supervisor (Claude + agents) analysis response.
    Also updates the cache so GET /analyze/latest returns this result.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: analyze_conflict(body.conflict))
    cache = _get_cache(request)
    cache[body.conflict] = {"result": result, "at": __import__("time").time()}
    return result
