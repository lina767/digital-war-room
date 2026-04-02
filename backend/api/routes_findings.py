"""
Finding archive routes.

Provides semantic search over the gated finding archive stored in pgvector.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from services.finding_archive_service import search_finding_archive
from services.storage_service import count_recent_embeddings, is_available

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


class FindingArchiveStatsResponse(BaseModel):
    conflict: Optional[str] = None
    hours: int = 72
    db_available: bool = False
    total: int = 0
    accepted: int = 0
    archived: int = 0


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


@router.get("/stats", response_model=FindingArchiveStatsResponse)
async def finding_archive_stats(
    conflict: Optional[str] = Query(None, max_length=120, description="Optional conflict filter."),
    hours: int = Query(72, ge=1, le=24 * 14, description="Window in hours (default 72)."),
) -> FindingArchiveStatsResponse:
    if not is_available():
        return FindingArchiveStatsResponse(conflict=conflict, hours=hours, db_available=False)

    total = await count_recent_embeddings(source="finding_archive", conflict=conflict, max_age_hours=hours)
    accepted = await count_recent_embeddings(
        source="finding_archive", conflict=conflict, max_age_hours=hours, decision="accepted"
    )
    archived = await count_recent_embeddings(
        source="finding_archive", conflict=conflict, max_age_hours=hours, decision="archived"
    )
    return FindingArchiveStatsResponse(
        conflict=conflict,
        hours=hours,
        db_available=True,
        total=total,
        accepted=accepted,
        archived=archived,
    )
