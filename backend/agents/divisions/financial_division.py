"""
Financial & Economic Division – FININT, ENERGY.

Owns:
- Tier 3: finint_ner_enrich (cross-division, depends on ner_extract)
- Tier 4: financial_summary
"""
import logging
from typing import Any, Callable, Dict, List

from ..dag_scheduler import DAGNode, ResultStore
from ..division import DivisionHead, DivisionAnomaly

logger = logging.getLogger(__name__)


class FinancialDivision(DivisionHead):
    name = "financial"
    agent_names = ["finint", "energy"]
    enrichment_nodes = ["finint_ner_enrich"]
    weight_map = {"finint": 0.55, "energy": 0.45}

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return [
            DAGNode(
                id="finint_ner_enrich",
                dependencies=["finint"],
                optional_deps=["ner_extract"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
            ),
        ]

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="financial_summary",
            dependencies=["finint_ner_enrich", "energy"],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {
            "finint_ner_enrich": self._exec_finint_ner,
        }

    @staticmethod
    def _exec_finint_ner(store: ResultStore) -> Dict[str, Any]:
        """Enrich FININT with NER PERSON/ORG entities for OFAC cross-ref."""
        finint = store.get("finint") or {}
        ner_registry = store.get("ner_extract")

        finint_data = finint if isinstance(finint, dict) else (
            finint.data if hasattr(finint, "data") and isinstance(finint.data, dict) else {}
        )

        if ner_registry is None or not hasattr(ner_registry, "get_by_type"):
            return finint_data

        try:
            from ..finint_agent import enrich_with_ner_entities
            persons = ner_registry.get_by_type("PERSON")
            orgs = ner_registry.get_by_type("ORG")
            entities = (
                [{"entity": e.entity, "type": "PERSON"} for e in persons] +
                [{"entity": e.entity, "type": "ORG"} for e in orgs]
            )
            return enrich_with_ner_entities(finint_data, entities)
        except Exception as e:
            logger.warning("finint_ner_enrich failed: %s", e)
            return finint_data

    def _detect_anomalies(self, agent_scores: Dict[str, float],
                          agents_failed: List[str]) -> List[DivisionAnomaly]:
        anomalies = super()._detect_anomalies(agent_scores, agents_failed)

        energy_s = agent_scores.get("energy", 0)
        finint_s = agent_scores.get("finint", 0)
        if energy_s > 60 and finint_s < 20:
            anomalies.append(DivisionAnomaly(
                type="contradiction",
                description=f"Energy markets stressed ({energy_s:.0f}) but FININT calm ({finint_s:.0f})",
                severity="medium",
                agents_involved=["energy", "finint"],
            ))

        return anomalies
