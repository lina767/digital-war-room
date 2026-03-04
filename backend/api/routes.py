import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from agents.supervisor import analyze_conflict


router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """
    POST /analyze
    Body: {"conflict": "US-Iran"}
    Returns the full supervisor (Claude + agents) analysis response.
    Runs in thread pool so the server stays responsive.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: analyze_conflict(request.conflict))
    return result
