"""PENTAGON agent entrypoint."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .pentagon_signals_agent import run_pentagon_signals_agent


def run_pentagon_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Entry point for the `pentagon` agent.
    Reuses the pentagon collection logic and normalizes the score key.
    """
    result = run_pentagon_signals_agent(conflict, peers=peers)
    if not isinstance(result, dict):
        return {"pentagon_score": 0.0, "summary": "PENTAGON: invalid upstream result.", "data_confidence": "degraded"}

    score = float(result.get("pentagon_score", 0.0) or 0.0)
    out = dict(result)
    out["pentagon_score"] = score
    if "summary" not in out:
        out["summary"] = "PENTAGON: reused pentagon data output."
    return out
