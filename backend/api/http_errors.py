"""
Small JSON error helpers shared by routes (consistent shape, less duplication).
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


def conflict_bad_request(exc: ValueError) -> JSONResponse:
    """400 response when ``sanitize_conflict`` rejects input."""
    return JSONResponse(status_code=400, content={"error": str(exc), "field": "conflict"})
