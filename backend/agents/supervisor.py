"""
Supervisor – Public API for conflict analysis.

Delegates to the DAG/CEO pipeline only. Legacy parallel collection has been removed.
"""

import logging
from typing import Any, Dict, Generator, Tuple

from .health_registry import get_health_registry
from .otel_callbacks import traced

_logger = logging.getLogger(__name__)


def run_analysis_streaming(conflict: str) -> Generator[Tuple[str, Any], None, None]:
    """
    Run analysis via DAG/CEO pipeline and yield (node_id, result) as each node completes.
    Final event is ("supervisor", full_result). Used by GET /api/analyze/stream for SSE.
    """
    from .ceo import analyze_conflict_dag_streaming

    for name, data in analyze_conflict_dag_streaming(conflict):
        yield ("supervisor", data) if name == "ceo_synthesis" else (name, data)


def analyze_conflict(conflict: str) -> Dict[str, Any]:
    """Public entrypoint – runs analysis via DAG/CEO pipeline only."""
    reg = get_health_registry()
    if reg:
        reg.clear()
    with traced("analysis.full", {"conflict": conflict}):
        from .ceo import analyze_conflict_dag

        return analyze_conflict_dag(conflict)
