from fastapi import APIRouter
from pydantic import BaseModel

from agents.supervisor import analyze_conflict


router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


@router.post("/analyze")
def analyze(request: AnalyzeRequest):
    """
    POST /analyze
    Body: {"conflict": "US-Iran"}
    Returns the full supervisor (Claude + FININT) analysis response.
    """
    result = analyze_conflict(request.conflict)
    return result
