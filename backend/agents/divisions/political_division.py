"""
Political & Legal Division – DIPLO, PROTEST.

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
    agent_names = ["diplo", "protest"]
    enrichment_nodes = []
    weight_map = {"diplo": 0.55, "protest": 0.45}

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return []

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="political_summary",
            dependencies=["diplo", "protest"],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {}

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        anomalies = super()._detect_anomalies(agent_scores, agents_failed)

        diplo_s = agent_scores.get("diplo", 0)
        protest_s = agent_scores.get("protest", 0)
        if protest_s > 60 and diplo_s > 50:
            anomalies.append(
                DivisionAnomaly(
                    type="threshold_breach",
                    description=f"High protest ({protest_s:.0f}) + sanctions activity ({diplo_s:.0f}) — possible crackdown indicator",
                    severity="high",
                    agents_involved=["diplo", "protest"],
                )
            )

        return anomalies
