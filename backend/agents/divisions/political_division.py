"""
Political & Legal Division – DIPLO.

No enrichment nodes of its own.
Tier 4: political_summary
"""

import logging
from typing import Callable, Dict, List

from ..dag_scheduler import DAGNode
from ..division import DivisionAnomaly, DivisionHead

logger = logging.getLogger(__name__)


class PoliticalDivision(DivisionHead):
    name = "political"
    agent_names = ["diplo"]
    enrichment_nodes = []
    weight_map = {"diplo": 1.0}

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return []

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="political_summary",
            dependencies=["diplo"],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {}

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        return super()._detect_anomalies(agent_scores, agents_failed)
