"""
Tests for DivisionHead base: score computation, anomaly detection, summary building.
"""

import pytest

from agents.dag_scheduler import ResultStore
from agents.division import DivisionAnomaly
from agents.divisions.financial_division import FinancialDivision
from agents.divisions.military_division import MilitaryDivision
from agents.divisions.political_division import PoliticalDivision
from agents.divisions.technical_division import TechnicalDivision


class TestWeightedScore:
    def test_all_agents_present(self):
        div = FinancialDivision()
        store = ResultStore()
        store.set("finint", {"escalation_score": 60})
        store.set("energy", {"energy_score": 40})

        result = div._execute_summary(store)
        expected = 60 * 0.55 + 40 * 0.45
        assert abs(result.score - expected) < 0.5

    def test_missing_agent_normalizes_weights(self):
        div = FinancialDivision()
        store = ResultStore()
        store.set("energy", {"energy_score": 50})

        result = div._execute_summary(store)
        assert result.score == pytest.approx(50.0, abs=0.5)
        assert "finint" in result.agents_failed


class TestAnomalyDetection:
    def test_contradiction_detected(self):
        div = MilitaryDivision()
        store = ResultStore()
        store.set("sigint", {"sigint_score": 80})
        store.set("geoint", {"geoint_score": 10})
        store.set("proximity", {"proximity_score": 30})
        store.set("chokepoint", {"chokepoint_score": 40})

        result = div._execute_summary(store)
        contradictions = [a for a in result.anomalies if a.type == "contradiction"]
        assert len(contradictions) > 0

    def test_threshold_breach(self):
        div = TechnicalDivision()
        store = ResultStore()
        store.set("techint", {"techint_score": 85})
        store.set("cyber", {"cyber_score": 80})

        result = div._execute_summary(store)
        breaches = [a for a in result.anomalies if a.type == "threshold_breach"]
        assert len(breaches) > 0

    def test_missing_agent_anomaly(self):
        div = PoliticalDivision()
        store = ResultStore()
        store.set("diplo", {"diplo_score": 40})

        result = div._execute_summary(store)
        missing = [a for a in result.anomalies if a.type == "missing_agent"]
        assert len(missing) == 1
        assert "protest" in missing[0].agents_involved


class TestDivisionDAGNodes:
    def test_military_nodes(self):
        div = MilitaryDivision()
        nodes = div.get_dag_nodes()
        node_ids = {n.id for n in nodes}
        assert "sigint" in node_ids
        assert "geoint" in node_ids
        assert "proximity" in node_ids
        assert "chokepoint" in node_ids
        assert "mil_sigint_chokepoint_enrich" in node_ids
        assert "geoint_ner_enrich" in node_ids
        assert "chokepoint_residual_enrich" in node_ids
        assert "military_summary" in node_ids

    def test_financial_nodes(self):
        div = FinancialDivision()
        nodes = div.get_dag_nodes()
        node_ids = {n.id for n in nodes}
        assert "finint" in node_ids
        assert "energy" in node_ids
        assert "finint_ner_enrich" in node_ids
        assert "financial_summary" in node_ids

    def test_political_has_no_enrichment(self):
        div = PoliticalDivision()
        nodes = div.get_dag_nodes()
        enrichment = [n for n in nodes if n.node_type == "enrichment"]
        assert len(enrichment) == 0

    def test_all_summaries_streamable(self):
        for DivClass in [MilitaryDivision, FinancialDivision, PoliticalDivision, TechnicalDivision]:
            div = DivClass()
            nodes = div.get_dag_nodes()
            summaries = [n for n in nodes if n.node_type == "division_summary"]
            assert all(n.streamable for n in summaries), f"{DivClass.name} summary not streamable"


class TestHaikuStrategy:
    def test_no_haiku_on_normal_scores(self):
        div = FinancialDivision()
        anomalies = []
        assert div._should_trigger_haiku(anomalies) is False

    def test_haiku_on_high_severity(self):
        div = FinancialDivision()
        anomalies = [DivisionAnomaly(type="contradiction", description="x", severity="high")]
        assert div._should_trigger_haiku(anomalies) is True

    def test_periodic_haiku(self):
        div = FinancialDivision()
        div.haiku_periodic_cycles = 2
        div._cycle_count = 2
        assert div._should_trigger_haiku([]) is True

    def test_periodic_haiku_off_cycle(self):
        div = FinancialDivision()
        div.haiku_periodic_cycles = 3
        div._cycle_count = 2
        assert div._should_trigger_haiku([]) is False
