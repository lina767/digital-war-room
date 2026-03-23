"""Tests for cross-agent quality gate."""

from agents.quality_gate import run_cross_agent_quality_gate


def test_gate_warns_on_score_spread():
    agent_results = {
        "finint": {"escalation_score": 10.0, "_meta": {"confidence": {"level": "high"},
            "data_freshness": "live", "sources": [], "fallback_used": False}},
        "news": {"news_score": 90.0, "_meta": {"confidence": {"level": "high"},
            "data_freshness": "live", "sources": [], "fallback_used": False}},
        "geoint": {"geoint_score": 10.0, "_meta": {"confidence": {"level": "high"},
            "data_freshness": "live", "sources": [], "fallback_used": False}},
        "sigint": {"sigint_score": 10.0},
        "satintel": {},
        "socmint": {},
        "techint": {},
        "cyber": {},
        "energy": {},
        "protest": {},
        "diplo": {},
        "proximity": {},
        "narrative": {},
        "chokepoint": {},
    }
    out = run_cross_agent_quality_gate("Test", agent_results, quality_fusion={}, synthesis_score=50.0)
    assert "quality_warnings" in out
    assert any("spread" in w.lower() for w in out["quality_warnings"])


def test_gate_finint_conflict_flag():
    agent_results = {
        "finint": {
            "escalation_score": 40.0,
            "brent": {"quality": {"conflict_flag": "price_spread"}},
        },
    }
    for k in (
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
    ):
        agent_results.setdefault(k, {})
    out = run_cross_agent_quality_gate("X", agent_results, quality_fusion={}, synthesis_score=0.0)
    assert any("finint.brent" in w or "conflict" in w.lower() for w in out["quality_warnings"])
