"""
Military & Maritime Division – SIGINT, GEOINT, PROXIMITY, CHOKEPOINT, PENTAGON_SIGNALS.

Owns:
- Tier 2: mil_sigint_chokepoint_enrich
- Tier 3: geoint_ner_enrich, chokepoint_residual_enrich (cross-division)
- Tier 4: military_summary
"""

import logging
from typing import Any, Callable, Dict, List

from ..dag_scheduler import DAGNode, ResultStore
from ..division import DivisionAnomaly, DivisionHead

logger = logging.getLogger(__name__)


class MilitaryDivision(DivisionHead):
    name = "military"
    agent_names = ["sigint", "geoint", "satintel", "proximity", "chokepoint", "pentagon_signals"]
    enrichment_nodes = [
        "mil_sigint_chokepoint_enrich",
        "geoint_ner_enrich",
        "chokepoint_residual_enrich",
    ]
    weight_map = {
        "sigint": 0.247,
        "geoint": 0.19,
        "satintel": 0.133,
        "chokepoint": 0.209,
        "proximity": 0.171,
        "pentagon_signals": 0.05,
    }

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return [
            DAGNode(
                id="mil_sigint_chokepoint_enrich",
                dependencies=["sigint", "chokepoint"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
            ),
            DAGNode(
                id="geoint_ner_enrich",
                dependencies=["geoint"],
                optional_deps=["ner_extract"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
            ),
            DAGNode(
                id="chokepoint_residual_enrich",
                dependencies=["mil_sigint_chokepoint_enrich"],
                optional_deps=["energy", "news", "diplo"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
            ),
        ]

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="military_summary",
            dependencies=[
                "mil_sigint_chokepoint_enrich",
                "chokepoint_residual_enrich",
                "geoint_ner_enrich",
                "proximity",
                "pentagon_signals",
            ],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {
            "mil_sigint_chokepoint_enrich": self._exec_mil_enrich,
            "geoint_ner_enrich": self._exec_geoint_ner_enrich,
            "chokepoint_residual_enrich": self._exec_chokepoint_residual,
        }

    @staticmethod
    def _exec_mil_enrich(store: ResultStore) -> Dict[str, Any]:
        """Merge SIGINT ships with CHOKEPOINT zone data (division-internal)."""
        sigint = store.get("sigint") or {}
        chokepoint = store.get("chokepoint") or {}

        sigint_data = (
            sigint
            if isinstance(sigint, dict)
            else (sigint.data if hasattr(sigint, "data") and isinstance(sigint.data, dict) else {})
        )
        cp_data = (
            chokepoint
            if isinstance(chokepoint, dict)
            else (chokepoint.data if hasattr(chokepoint, "data") and isinstance(chokepoint.data, dict) else {})
        )

        try:
            from ..chokepoint_agent import enrich_chokepoints

            # Tier-2 enrichment intentionally runs before cross-division data exists.
            # Pass empty placeholders for newer args expected by enrich_chokepoints.
            enriched = enrich_chokepoints(
                cp_data,
                sigint_data,
                {},
                {},
                {},
            )
            return {"sigint": sigint_data, "chokepoint_enriched": enriched}
        except Exception as e:
            logger.warning("mil_sigint_chokepoint_enrich failed: %s", e)
            return {"sigint": sigint_data, "chokepoint_enriched": cp_data}

    @staticmethod
    def _exec_geoint_ner_enrich(store: ResultStore) -> Dict[str, Any]:
        """Enrich GEOINT with NER LOCATION entities for hotspot correlation."""
        geoint = store.get("geoint") or {}
        ner_registry = store.get("ner_extract")

        geoint_data = (
            geoint
            if isinstance(geoint, dict)
            else (geoint.data if hasattr(geoint, "data") and isinstance(geoint.data, dict) else {})
        )

        if ner_registry is None or not hasattr(ner_registry, "get_by_type"):
            return geoint_data

        try:
            from ..geoint_agent import enrich_with_ner_entities

            locations = [e.entity for e in ner_registry.get_by_type("LOCATION")]
            entities = [{"entity": loc, "type": "LOCATION"} for loc in locations]
            return enrich_with_ner_entities(geoint_data, entities)
        except Exception as e:
            logger.warning("geoint_ner_enrich failed: %s", e)
            return geoint_data

    @staticmethod
    def _exec_chokepoint_residual(store: ResultStore) -> Dict[str, Any]:
        """Residual chokepoint enrichment with cross-division data."""
        mil_enrich = store.get("mil_sigint_chokepoint_enrich") or {}
        energy = store.get("energy")
        news = store.get("news")
        diplo = store.get("diplo")

        cp_enriched = mil_enrich.get("chokepoint_enriched", {}) if isinstance(mil_enrich, dict) else {}

        energy_data = (
            energy
            if isinstance(energy, dict)
            else (energy.data if hasattr(energy, "data") and isinstance(energy.data, dict) else {})
        )
        _news_data = (
            news
            if isinstance(news, dict)
            else (news.data if hasattr(news, "data") and isinstance(news.data, dict) else {})
        )
        _diplo_data = (
            diplo
            if isinstance(diplo, dict)
            else (diplo.data if hasattr(diplo, "data") and isinstance(diplo.data, dict) else {})
        )

        result = dict(cp_enriched)
        if energy_data:
            brent_pct = None
            for c in energy_data.get("commodities") or []:
                if c.get("symbol") == "BRENT":
                    brent_pct = c.get("change_pct")
            result["brent_change_pct"] = brent_pct
        return result

    # -- Anomaly detection overrides ----------------------------------------

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        anomalies = super()._detect_anomalies(agent_scores, agents_failed)

        sigint_s = agent_scores.get("sigint", 0)
        geoint_s = agent_scores.get("geoint", 0)
        if sigint_s > 60 and geoint_s < 20:
            anomalies.append(
                DivisionAnomaly(
                    type="contradiction",
                    description=f"SIGINT high ({sigint_s:.0f}) but GEOINT low ({geoint_s:.0f}) — possible covert activity",
                    severity="high",
                    agents_involved=["sigint", "geoint"],
                )
            )

        return anomalies
