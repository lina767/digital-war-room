"""
Finding archive routes.

Provides semantic search over the gated finding archive stored in pgvector.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from services.finding_archive_service import search_finding_archive

router = APIRouter(prefix="/api/findings")


Decision = Optional[Literal["accepted", "archived"]]


class FindingSearchResponse(BaseModel):
    query: str
    conflict: Optional[str] = None
    decision: Decision = None
    hours: int = 72
    threshold: float = 0.75
    top_k: int = 10
    matches: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/search", response_model=FindingSearchResponse)
async def search_findings(
    q: str = Query(..., min_length=3, max_length=800, description="Search query (semantic embedding)."),
    conflict: Optional[str] = Query(None, max_length=120, description="Optional conflict filter."),
    decision: Decision = Query(None, description='Optional filter: "accepted" or "archived".'),
    hours: int = Query(72, ge=1, le=24 * 14, description="Search window in hours (default 72)."),
    threshold: float = Query(0.75, ge=0.0, le=1.0, description="Cosine similarity threshold."),
    top_k: int = Query(10, ge=1, le=50, description="Max results."),
) -> FindingSearchResponse:
    matches = await search_finding_archive(
        query=q,
        conflict=conflict,
        hours=hours,
        threshold=threshold,
        top_k=top_k,
        decision=decision,
    )
    return FindingSearchResponse(
        query=q,
        conflict=conflict,
        decision=decision,
        hours=hours,
        threshold=threshold,
        top_k=top_k,
        matches=matches,
    )

