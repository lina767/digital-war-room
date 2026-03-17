"""
Technical & Cyber Division – TECHINT, CYBER.

No enrichment nodes (CVE enrichment runs agent-internally).
Tier 4: technical_summary
"""

import logging
from typing import Callable, Dict, List

from ..dag_scheduler import DAGNode
from ..division import DivisionAnomaly, DivisionHead

logger = logging.getLogger(__name__)


class TechnicalDivision(DivisionHead):
    name = "technical"
    agent_names = ["techint", "cyber"]
    enrichment_nodes = []
    weight_map = {"techint": 0.50, "cyber": 0.50}

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return []

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="technical_summary",
            dependencies=["techint", "cyber"],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {}

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        anomalies = super()._detect_anomalies(agent_scores, agents_failed)

        techint_s = agent_scores.get("techint", 0)
        cyber_s = agent_scores.get("cyber", 0)
        if techint_s > 50 and cyber_s > 50:
            anomalies.append(
                DivisionAnomaly(
                    type="threshold_breach",
                    description=f"IODA outage ({techint_s:.0f}) correlates with cyber activity ({cyber_s:.0f})",
                    severity="high",
                    agents_involved=["techint", "cyber"],
                )
            )

        return anomalies
