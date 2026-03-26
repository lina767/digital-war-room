"""
Tests for InformationDivision: NER extract, prefilter, summary, anomaly detection.
"""

from agents.dag_scheduler import ResultStore
from agents.divisions.information_division import InformationDivision
from agents.entity_registry import EntityRegistry


def _mock_news_result(score=45, entities=None):
    return {
        "news_score": score,
        "articles": [{"title": "Iran missile test", "source": "reuters"}],
        "entities": entities
        or [
            {"entity": "Iran", "type": "LOCATION", "confidence": 0.95},
            {"entity": "IRGC", "type": "ORG", "confidence": 0.88},
            {"entity": "Khamenei", "type": "PERSON", "confidence": 0.92},
        ],
        "summary": "Test news",
    }


def _mock_socmint_result(score=40, entities=None):
    return {
        "socmint_score": score,
        "top_signals": [{"text": "Breaking: escalation in region"}],
        "entities": entities
        or [
            {"entity": "Hezbollah", "type": "ORG", "confidence": 0.85},
            {"entity": "Iran", "type": "LOCATION", "confidence": 0.70},
        ],
        "summary": "Test socmint",
    }


def _mock_narrative_result(score=30):
    return {
        "narrative_score": score,
        "synthesis_probability": 0.4,
        "summary": "Narrative analysis",
    }


def _mock_mediaint_result(score=25):
    return {
        "mediaint_score": score,
        "media_assets": [],
        "near_duplicate_clusters": [],
        "exif_gps_count": 0,
        "video_keyframes_extracted": 0,
        "vision_analysis_count": 0,
        "ffmpeg_available": False,
        "summary": "MEDIAINT mock",
    }


class TestNERExtract:
    def test_extracts_entities_from_news_and_socmint(self):
        store = ResultStore()
        store.set("news", _mock_news_result())
        store.set("socmint", _mock_socmint_result())

        registry = InformationDivision._exec_ner_extract(store)
        assert isinstance(registry, EntityRegistry)
        assert registry.count > 0

    def test_deduplicates_across_sources(self):
        store = ResultStore()
        store.set(
            "news",
            _mock_news_result(
                entities=[
                    {"entity": "Iran", "type": "LOCATION"},
                ]
            ),
        )
        store.set(
            "socmint",
            _mock_socmint_result(
                entities=[
                    {"entity": "Iran", "type": "LOCATION"},
                ]
            ),
        )

        registry = InformationDivision._exec_ner_extract(store)
        assert registry.count == 1

    def test_alias_dedup(self):
        store = ResultStore()
        store.set(
            "news",
            _mock_news_result(
                entities=[
                    {"entity": "IRGC", "type": "ORG"},
                ]
            ),
        )
        store.set(
            "socmint",
            _mock_socmint_result(
                entities=[
                    {"entity": "Islamic Revolutionary Guard Corps", "type": "ORG"},
                ]
            ),
        )

        registry = InformationDivision._exec_ner_extract(store)
        assert registry.count == 1
        assert registry.get_all()[0].entity == "IRGC"

    def test_handles_missing_agent(self):
        store = ResultStore()
        store.set("news", _mock_news_result())

        registry = InformationDivision._exec_ner_extract(store)
        assert registry.count > 0

    def test_handles_empty_entities(self):
        store = ResultStore()
        store.set("news", {"entities": []})
        store.set("socmint", {"entities": []})

        registry = InformationDivision._exec_ner_extract(store)
        assert registry.count == 0

    def test_entity_types_preserved(self):
        store = ResultStore()
        store.set("news", _mock_news_result())
        store.set("socmint", {"entities": []})

        registry = InformationDivision._exec_ner_extract(store)
        types = {e.type for e in registry.get_all()}
        assert "LOCATION" in types
        assert "ORG" in types
        assert "PERSON" in types


class TestPrefilter:
    def test_returns_valid_structure(self):
        store = ResultStore()
        store.set("news", _mock_news_result())
        store.set("socmint", _mock_socmint_result())

        result = InformationDivision._exec_prefilter(store)
        assert "news" in result
        assert "socmint" in result
        assert "filtered" in result

    def test_handles_missing_agent(self):
        store = ResultStore()
        store.set("news", _mock_news_result())

        result = InformationDivision._exec_prefilter(store)
        assert "news" in result


class TestSummaryNode:
    def test_computes_weighted_score(self):
        div = InformationDivision()
        store = ResultStore()
        store.set("news", _mock_news_result(score=60))
        store.set("socmint", _mock_socmint_result(score=40))
        store.set("mediaint", _mock_mediaint_result(score=30))
        store.set("narrative", _mock_narrative_result(score=20))

        result = div._execute_summary(store)
        assert result.division == "information"
        assert result.score > 0
        assert "news" in result.agent_scores
        assert "socmint" in result.agent_scores
        assert "mediaint" in result.agent_scores
        assert "narrative" in result.agent_scores

    def test_handles_missing_agent(self):
        div = InformationDivision()
        store = ResultStore()
        store.set("news", _mock_news_result(score=50))
        store.set("socmint", _mock_socmint_result(score=30))
        store.set("mediaint", _mock_mediaint_result(score=20))

        result = div._execute_summary(store)
        assert "narrative" in result.agents_failed
        assert result.score > 0

    def test_detects_sentiment_divergence(self):
        div = InformationDivision()
        store = ResultStore()
        store.set("news", _mock_news_result(score=80))
        store.set("socmint", _mock_socmint_result(score=20))
        store.set("mediaint", _mock_mediaint_result(score=25))
        store.set("narrative", _mock_narrative_result())

        result = div._execute_summary(store)
        contradiction = [a for a in result.anomalies if a.type == "contradiction"]
        assert len(contradiction) > 0

    def test_no_anomaly_for_similar_scores(self):
        div = InformationDivision()
        store = ResultStore()
        store.set("news", _mock_news_result(score=45))
        store.set("socmint", _mock_socmint_result(score=42))
        store.set("mediaint", _mock_mediaint_result(score=40))
        store.set("narrative", _mock_narrative_result(score=40))

        result = div._execute_summary(store)
        contradictions = [a for a in result.anomalies if a.type == "contradiction"]
        assert len(contradictions) == 0


class TestDAGNodes:
    def test_info_division_produces_correct_nodes(self):
        div = InformationDivision()
        nodes = div.get_dag_nodes()
        node_ids = {n.id for n in nodes}
        assert "news" in node_ids
        assert "socmint" in node_ids
        assert "mediaint" in node_ids
        assert "narrative" in node_ids
        assert "ner_extract" in node_ids
        assert "prefilter_summarize" in node_ids
        assert "information_summary" in node_ids

    def test_ner_extract_depends_on_news_socmint(self):
        div = InformationDivision()
        nodes = {n.id: n for n in div.get_dag_nodes()}
        ner = nodes["ner_extract"]
        assert "news" in ner.dependencies
        assert "socmint" in ner.dependencies

    def test_summary_is_streamable(self):
        div = InformationDivision()
        nodes = {n.id: n for n in div.get_dag_nodes()}
        summary = nodes["information_summary"]
        assert summary.streamable is True

    def test_agent_nodes_streamable(self):
        div = InformationDivision()
        nodes = {n.id: n for n in div.get_dag_nodes()}
        assert nodes["news"].streamable is True
        assert nodes["socmint"].streamable is True
        assert nodes["mediaint"].streamable is True

    def test_mediaint_depends_on_socmint(self):
        div = InformationDivision()
        nodes = {n.id: n for n in div.get_dag_nodes()}
        assert "socmint" in nodes["mediaint"].dependencies

    def test_enrichment_not_streamable(self):
        div = InformationDivision()
        nodes = {n.id: n for n in div.get_dag_nodes()}
        assert nodes["ner_extract"].streamable is False
