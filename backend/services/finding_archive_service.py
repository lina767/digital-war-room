"""
Finding Archive Service — semantic search over gated findings.

Backed by pgvector via storage_service when DATABASE_URL is configured.
Falls back gracefully (returns empty results) if DB or embeddings are unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


async def search_finding_archive(
    *,
    query: str,
    conflict: Optional[str] = None,
    hours: int = 72,
    threshold: float = 0.75,
    top_k: int = 10,
    decision: Optional[str] = None,  # "accepted" | "archived" | None (both)
) -> List[Dict[str, Any]]:
    """
    Semantic search in the finding archive.
    Returns list of matches with similarity and stored metadata.
    """
    if not query or not query.strip():
        return []

    try:
        from services.hf_service import embed
        from services.storage_service import find_similar_recent, is_available
    except Exception:
        return []

    if not is_available():
        return []

    vecs = await embed([query.strip()[:800]])
    if not vecs or not vecs[0]:
        return []

    rows = await find_similar_recent(
        vecs[0],
        top_k=max(1, int(top_k)),
        source="finding_archive",
        conflict=conflict,
        threshold=float(threshold),
        max_age_hours=max(1, int(hours)),
    )

    if decision:
        d = decision.strip().lower()
        rows = [r for r in rows if isinstance(r, dict) and (r.get("metadata") or {}).get("decision") == d]

    return rows

