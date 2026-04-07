from agents.research_trigger import evaluate_research_trigger


def test_research_trigger_detects_missing_required_fields():
    decision = evaluate_research_trigger(
        conflict="Iran",
        agent_results={
            "finint": {"escalation_score": 40.0},
            "sigint": {"sigint_score": 50.0, "aircraft": []},
            "news": {"news_score": 55.0, "articles": []},
            "geoint": {"geoint_score": 60.0, "anomalies": []},
            "diplo": {"diplo_score": 20.0, "ofac_sdn": {}},
        },
        data_quality_gate={},
    )
    assert decision.triggered is True
    assert decision.missing_required_fields_count >= 1
    assert any(r.trigger == "missing_required_fields" for r in decision.reasons)


def test_research_trigger_detects_conflict_spread():
    decision = evaluate_research_trigger(
        conflict="Iran",
        agent_results={
            "finint": {"escalation_score": 5.0, "dq_confidence": 75.0, "data_freshness": "recent"},
            "sigint": {"sigint_score": 92.0, "dq_confidence": 70.0, "data_freshness": "recent"},
            "news": {"news_score": 10.0, "dq_confidence": 65.0, "data_freshness": "recent"},
            "geoint": {"geoint_score": 90.0, "dq_confidence": 61.0, "data_freshness": "recent"},
            "diplo": {"diplo_score": 8.0, "ofac_sdn": {"x": 1}, "dq_confidence": 68.0, "data_freshness": "recent"},
        },
        data_quality_gate={},
    )
    assert decision.triggered is True
    assert decision.score_spread > 40
    assert any(r.trigger == "agent_conflict" for r in decision.reasons)
