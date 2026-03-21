"""
Tests for CEO orchestrator: synthesis, delta-aware prompt, division-failure handling.
"""

from agents.ceo import _build_ceo_prompt, _ceo_synthesize
from agents.dag_scheduler import ResultStore
from agents.division import DivisionAnomaly, DivisionResult
from agents.divisions import (
    FinancialDivision,
    InformationDivision,
    MilitaryDivision,
    PoliticalDivision,
    TechnicalDivision,
)
from agents.entity_registry import EntityRegistry, NEREntity


def _mock_division_result(name, score=50.0, anomalies=None):
    return DivisionResult(
        division=name,
        score=score,
        agent_scores={f"{name}_agent1": score},
        anomalies=anomalies or [],
        summary=f"{name} summary: score {score}",
        agents_ok=[f"{name}_agent1"],
    )


def _populated_store():
    """Build a store with all division summaries populated."""
    store = ResultStore(cycle_id="test", conflict="Iran")
    store.set("military_summary", _mock_division_result("military", 72))
    store.set("financial_summary", _mock_division_result("financial", 45))
    store.set("information_summary", _mock_division_result("information", 58))
    store.set("political_summary", _mock_division_result("political", 28))
    store.set("technical_summary", _mock_division_result("technical", 32))
    store.set("compliance_build", {"compliance": {}, "alerts": []})
    store.set("acled_refs", [])
    return store


class TestCEOSynthesis:
    def test_produces_valid_response(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _populated_store()
        divisions = [
            MilitaryDivision(),
            FinancialDivision(),
            InformationDivision(),
            PoliticalDivision(),
            TechnicalDivision(),
        ]
        result = _ceo_synthesize("Iran", divisions, store)

        assert "escalation_score" in result
        assert "threat_level" in result
        assert "key_findings" in result
        assert "scenarios" in result
        assert "summary" in result
        assert "narrative_story" in result
        assert isinstance(result["narrative_story"], str)
        assert "compliance" in result
        assert "alerts" in result
        assert result["conflict"] == "Iran"

    def test_composite_score_is_weighted(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _populated_store()
        divisions = [
            MilitaryDivision(),
            FinancialDivision(),
            InformationDivision(),
            PoliticalDivision(),
            TechnicalDivision(),
        ]
        result = _ceo_synthesize("Iran", divisions, store)

        expected = 72 * 0.30 + 45 * 0.18 + 58 * 0.22 + 28 * 0.14 + 32 * 0.16
        assert abs(result["escalation_score"] - expected) < 1.0

    def test_threat_level_mapping(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"

        for score, expected_level in [(85, "CRITICAL"), (65, "HIGH"), (45, "ELEVATED"), (25, "LOW"), (10, "MINIMAL")]:
            store = ResultStore(conflict="test")
            for name in ["military", "financial", "information", "political", "technical"]:
                store.set(f"{name}_summary", _mock_division_result(name, score))
            store.set("compliance_build", {"compliance": {}, "alerts": []})
            store.set("acled_refs", [])
            divisions = [
                MilitaryDivision(),
                FinancialDivision(),
                InformationDivision(),
                PoliticalDivision(),
                TechnicalDivision(),
            ]
            result = _ceo_synthesize("test", divisions, store)
            assert result["threat_level"] == expected_level, (
                f"score {score}: expected {expected_level}, got {result['threat_level']}"
            )

    def test_handles_missing_division(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = ResultStore(conflict="Iran")
        store.set("military_summary", _mock_division_result("military", 60))
        store.set("financial_summary", _mock_division_result("financial", 40))
        store.set("compliance_build", {"compliance": {}, "alerts": []})
        store.set("acled_refs", [])

        divisions = [
            MilitaryDivision(),
            FinancialDivision(),
            InformationDivision(),
            PoliticalDivision(),
            TechnicalDivision(),
        ]
        result = _ceo_synthesize("Iran", divisions, store)
        assert result["escalation_score"] > 0
        assert result["threat_level"] in ("MINIMAL", "LOW", "ELEVATED", "HIGH", "CRITICAL")

    def test_anomaly_findings_included(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = ResultStore(conflict="Iran")
        anomaly = DivisionAnomaly(
            type="contradiction",
            description="SIGINT high but GEOINT low",
            severity="high",
        )
        store.set("military_summary", _mock_division_result("military", 72, anomalies=[anomaly]))
        store.set("financial_summary", _mock_division_result("financial", 45))
        store.set("information_summary", _mock_division_result("information", 58))
        store.set("political_summary", _mock_division_result("political", 28))
        store.set("technical_summary", _mock_division_result("technical", 32))
        store.set("compliance_build", {"compliance": {}, "alerts": []})
        store.set("acled_refs", [])

        divisions = [
            MilitaryDivision(),
            FinancialDivision(),
            InformationDivision(),
            PoliticalDivision(),
            TechnicalDivision(),
        ]
        result = _ceo_synthesize("Iran", divisions, store)
        assert any("SIGINT" in f for f in result["key_findings"])

    def test_includes_divisions_metadata(self):
        import os

        os.environ["USE_RULE_BASED_SUPERVISOR"] = "1"
        store = _populated_store()
        divisions = [
            MilitaryDivision(),
            FinancialDivision(),
            InformationDivision(),
            PoliticalDivision(),
            TechnicalDivision(),
        ]
        result = _ceo_synthesize("Iran", divisions, store)
        assert "divisions" in result
        assert "military" in result["divisions"]


class TestCEOPrompt:
    def test_prompt_contains_divisions(self):
        store = _populated_store()
        dr = {
            "military": _mock_division_result("military", 72),
            "financial": _mock_division_result("financial", 45),
        }
        prompt = _build_ceo_prompt("Iran", dr, 58.5, store)
        assert "Military" in prompt
        assert "Financial" in prompt
        assert "72" in prompt

    def test_prompt_contains_entities(self):
        store = _populated_store()
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        reg.add(NEREntity(entity="IRGC", type="ORG", source_agent="socmint"))
        store.set("ner_extract", reg)

        dr = {"military": _mock_division_result("military", 60)}
        prompt = _build_ceo_prompt("Iran", dr, 60, store)
        assert "LOCATION" in prompt
        assert "Iran" in prompt

    def test_prompt_shows_anomalies(self):
        store = _populated_store()
        anomaly = DivisionAnomaly(
            type="contradiction",
            description="Score divergence",
            severity="high",
            agents_involved=["sigint", "geoint"],
        )
        dr = {"military": _mock_division_result("military", 72, anomalies=[anomaly])}
        prompt = _build_ceo_prompt("Iran", dr, 72, store)
        assert "Score divergence" in prompt
        assert "high" in prompt
