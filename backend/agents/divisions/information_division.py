"""
Information & Media Division – NEWS, SOCMINT, NARRATIVE.

Owns:
- Tier 2 enrichment: ner_extract, prefilter_summarize
- Tier 4: information_summary
- Exports: EntityRegistry (via ner_extract node)
"""

import logging
from typing import Any, Callable, Dict, List

from ..dag_scheduler import DAGNode, ResultStore
from ..division import DivisionAnomaly, DivisionHead
from ..entity_registry import EntityRegistry, NEREntity

logger = logging.getLogger(__name__)


class InformationDivision(DivisionHead):
    name = "information"
    agent_names = ["news", "socmint", "narrative"]
    enrichment_nodes = ["ner_extract", "prefilter_summarize"]
    weight_map = {"news": 0.40, "socmint": 0.35, "narrative": 0.25}

    def _get_enrichment_nodes(self) -> List[DAGNode]:
        return [
            DAGNode(
                id="ner_extract",
                dependencies=["news", "socmint"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
                streamable=False,
            ),
            DAGNode(
                id="prefilter_summarize",
                dependencies=["news", "socmint"],
                node_type="enrichment",
                owner_division=self.name,
                timeout_s=15.0,
                streamable=False,
            ),
        ]

    def _get_summary_node(self) -> DAGNode:
        return DAGNode(
            id="information_summary",
            dependencies=["prefilter_summarize", "ner_extract", "narrative"],
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        return {
            "ner_extract": self._exec_ner_extract,
            "prefilter_summarize": self._exec_prefilter,
        }

    # -- Enrichment executors -----------------------------------------------

    @staticmethod
    def _exec_ner_extract(store: ResultStore) -> EntityRegistry:
        """Extract NER entities from NEWS + SOCMINT results.

        Populates an EntityRegistry and stores it in the ResultStore
        so downstream nodes (finint_ner_enrich, geoint_ner_enrich, CEO) can use it.
        """
        registry = EntityRegistry()

        news_result = store.get("news")
        socmint_result = store.get("socmint")

        for source_name, result in [("news", news_result), ("socmint", socmint_result)]:
            if result is None:
                continue
            entities_raw = _extract_entities_list(result)
            for ent_dict in entities_raw:
                entity_text = ent_dict.get("entity", "").strip()
                entity_type = ent_dict.get("type", "UNKNOWN").upper()
                if not entity_text:
                    continue
                registry.add(
                    NEREntity(
                        entity=entity_text,
                        type=entity_type,
                        source_agent=source_name,
                        confidence=float(ent_dict.get("confidence", 1.0)),
                    )
                )

        registry.deduplicate()
        return registry

    @staticmethod
    def _exec_prefilter(store: ResultStore) -> Dict[str, Any]:
        """Pre-filter and summarize NEWS + SOCMINT before LLM synthesis.

        Attempts to use haiku_service for zero-shot classification and
        summarization. Falls back to pass-through if unavailable.
        """
        news_result = store.get("news") or {}
        socmint_result = store.get("socmint") or {}

        news_data = _as_dict(news_result)
        socmint_data = _as_dict(socmint_result)

        try:
            from services.haiku_service import classify, is_haiku_failed, summarize

            if is_haiku_failed():
                raise ImportError("haiku unavailable")
        except ImportError:
            return {"news": news_data, "socmint": socmint_data, "filtered": False}

        import os

        from ..utils import run_async

        threshold = float(os.getenv("CLASSIFY_CONFIDENCE_THRESHOLD", "0.3"))
        char_threshold = int(os.getenv("SUMMARIZE_CHAR_THRESHOLD", "600"))

        for key, data in [("articles", news_data), ("top_signals", socmint_data)]:
            items = data.get(key, []) if isinstance(data, dict) else []
            filtered = []
            for item in items:
                if not isinstance(item, dict):
                    filtered.append(item)
                    continue
                text = item.get("title", "") or item.get("text", "") or ""
                if not text:
                    filtered.append(item)
                    continue
                try:
                    cat = run_async(classify(text))
                except Exception:
                    cat = None
                if cat and cat.get("label") == "other" and cat.get("score", 0) < threshold:
                    continue
                if len(text) > char_threshold:
                    try:
                        short = run_async(summarize(text))
                    except Exception:
                        short = None
                    if short:
                        item["summary"] = short
                filtered.append(item)
            if isinstance(data, dict):
                data[key] = filtered

        return {"news": news_data, "socmint": socmint_data, "filtered": True}

    # -- Anomaly detection overrides ----------------------------------------

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        anomalies = super()._detect_anomalies(agent_scores, agents_failed)

        news_score = agent_scores.get("news", 0)
        socmint_score = agent_scores.get("socmint", 0)
        if abs(news_score - socmint_score) > 40:
            anomalies.append(
                DivisionAnomaly(
                    type="contradiction",
                    description=f"NEWS/SOCMINT sentiment divergence: news={news_score:.0f} vs socmint={socmint_score:.0f}",
                    severity="medium",
                    agents_involved=["news", "socmint"],
                )
            )

        return anomalies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_entities_list(result: Any) -> List[Dict]:
    """Get entities list from agent result (dict or Pydantic model)."""
    if isinstance(result, dict):
        return result.get("entities", [])
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data.get("entities", [])
    if hasattr(result, "entities"):
        return result.entities
    return []


def _as_dict(result: Any) -> Dict:
    """Coerce an agent result to a plain dict."""
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data
    return {}
