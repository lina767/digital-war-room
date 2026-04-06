"""
PROTEST agent stub — replaces removed `protest_agent.py`.

Preserves the same `run_protest_agent` contract for the DAG, CEO synthesis, and API.
Returns a zeroed `ProtestResult` shape with degraded metadata.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .contracts import get_agent_fallback
from .health_registry import get_health_registry
from .utils import SourceResult, build_agent_meta, utc_now_iso


def run_protest_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return empty protest payload; full ACLED/GDELT implementation removed."""
    fetched_at = utc_now_iso()
    start = time.perf_counter()
    out = get_agent_fallback("protest")
    out["summary"] = "PROTEST: Disabled — civil-society agent implementation removed."
    out["data_freshness"] = "unavailable"
    duration_ms = int((time.perf_counter() - start) * 1000)
    sr = SourceResult(name="protest_stub", status="degraded", fetched_at=fetched_at, record_count=0)
    reg = get_health_registry()
    if reg:
        reg.record_result(sr.name, "protest", sr)
    out["_meta"] = build_agent_meta(
        "protest",
        fetched_at,
        duration_ms,
        [sr],
        fallback_used=True,
        error_summary="protest_agent module removed; stub only",
        has_any_data=False,
        data_confidence="degraded",
    )
    return out
