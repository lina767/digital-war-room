"""
Integration test: verify the full DAG produces a response format identical
to the legacy supervisor.analyze_conflict() API shape.
"""

import os

from agents.ceo import (
    CEO_WEIGHTS,
    _all_divisions,
    _build_full_dag,
    _ceo_synthesize,
)
from agents.dag_scheduler import DAGScheduler, ResultStore
from agents.division import DivisionResult

EXPECTED_RESPONSE_KEYS = {
    "conflict",
    "escalation_score",
    "threat_level",
    "key_findings",
    "key_findings_context",
    "key_findings_confidence",
    "corroborated_patterns",
    "scenarios",
    "summary",
    "actors",
    "predictive",
    "compliance",
    "alerts",
    "divisions",
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
}


def _mock_agent_result(agent_name, score=40):
    score_field = "escalation_score" if agent_name == "finint" else f"{agent_name}_score"
    return {score_field: score, "summary": f"{agent_name} mock"}


def _mock_store():
    """Build a fully populated mock store as if all agents + enrichment ran."""
    store = ResultStore(cycle_id="test-int", conflict="Iran")
    for name in [
        "sigint",
        "geoint",
        "satintel",
        "proximity",
        "chokepoint",
        "finint",
        "energy",
        "news",
        "socmint",
        "narrative",
        "diplo",
        "protest",
        "techint",
        "cyber",
    ]:
        store.set(name, _mock_agent_result(name))

    store.set("acled_refs", [])
    store.set("compliance_build", {"compliance": {}, "alerts": []})

    store.set("ner_extract", None)
    store.set("prefilter_summarize", {"news": {}, "socmint": {}, "filtered": False})
    store.set("mil_sigint_chokepoint_enrich", {"sigint": {}, "chokepoint_enriched": {}})
    store.set("geoint_ner_enrich", {})
    store.set("chokepoint_residual_enrich", {})
    store.set("finint_ner_enrich", {})

    for div_name in ["military", "financial", "information", "political", "technical"]:
        store.set(
            f"{div_name}_summary",
            DivisionResult(
                division=div_name,
                score=40.0,
                agent_scores={},
                summary=f"{div_name} summary",
            ),
        )

    return store


class TestResponseFormat:
    def test_response_has_all_expected_keys(self):
        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _mock_store()
        divisions = _all_divisions()
        result = _ceo_synthesize("Iran", divisions, store)

        missing = EXPECTED_RESPONSE_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_agent_data_preserved_in_response(self):
        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _mock_store()
        divisions = _all_divisions()
        result = _ceo_synthesize("Iran", divisions, store)

        assert result["sigint"]["sigint_score"] == 40
        assert result["news"]["news_score"] == 40
        assert result["finint"]["escalation_score"] == 40

    def test_escalation_score_is_numeric(self):
        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _mock_store()
        divisions = _all_divisions()
        result = _ceo_synthesize("Iran", divisions, store)

        assert isinstance(result["escalation_score"], (int, float))

    def test_threat_level_is_valid(self):
        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _mock_store()
        divisions = _all_divisions()
        result = _ceo_synthesize("Iran", divisions, store)

        assert result["threat_level"] in ("MINIMAL", "LOW", "ELEVATED", "HIGH", "CRITICAL")


class TestFullDAGStructure:
    def test_dag_builds_without_error(self):
        divisions = _all_divisions()
        nodes, executors = _build_full_dag(divisions)
        assert len(nodes) > 20
        node_ids = {n.id for n in nodes}
        assert "ceo_synthesis" in node_ids
        assert "military_summary" in node_ids
        assert "financial_summary" in node_ids
        assert "information_summary" in node_ids
        assert "political_summary" in node_ids
        assert "technical_summary" in node_ids

    def test_dag_can_be_scheduled(self):
        divisions = _all_divisions()
        nodes, _ = _build_full_dag(divisions)
        scheduler = DAGScheduler(nodes)
        assert scheduler is not None

    def test_ceo_depends_on_all_summaries(self):
        divisions = _all_divisions()
        nodes, _ = _build_full_dag(divisions)
        ceo = next(n for n in nodes if n.id == "ceo_synthesis")
        for div_name in ["military", "financial", "information", "political", "technical"]:
            assert f"{div_name}_summary" in ceo.dependencies

    def test_all_agent_nodes_are_streamable(self):
        divisions = _all_divisions()
        nodes, _ = _build_full_dag(divisions)
        agent_nodes = [n for n in nodes if n.node_type == "agent"]
        for n in agent_nodes:
            assert n.streamable, f"Agent node '{n.id}' should be streamable"

    def test_enrichment_nodes_not_streamable(self):
        divisions = _all_divisions()
        nodes, _ = _build_full_dag(divisions)
        enrichment_nodes = [n for n in nodes if n.node_type == "enrichment"]
        for n in enrichment_nodes:
            assert not n.streamable, f"Enrichment node '{n.id}' should not be streamable"


class TestDivisionWeights:
    def test_weights_sum_to_one(self):
        total = sum(CEO_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_all_divisions_have_weights(self):
        for div in _all_divisions():
            assert div.name in CEO_WEIGHTS, f"Division '{div.name}' missing CEO weight"
