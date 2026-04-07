"""Tests for cross-feed pattern anomaly heuristics."""

from agents.pattern_anomalies import compute_pattern_flags


def _base_result(**overrides):
    r = {
        "escalation_score": 50.0,
        "news": {"articles": [{"title": "Markets steady", "description": ""}]},
        "sigint": {"conflict_reports": [], "aircraft": [], "ships": []},
        "socmint": {"top_signals": []},
    }
    r.update(overrides)
    return r


def test_no_previous_elevated_military_chatter():
    cur = _base_result(
        news={
            "articles": [
                {"title": "Missile test and military drills near border", "description": "troops deployment"},
            ]
            * 25
        },
        sigint={
            "conflict_reports": [{"title": "Defense ministry statement on strikes"}] * 5,
            "aircraft": [],
            "ships": [],
        },
        socmint={"top_signals": ["navy fleet movement"] * 8},
    )
    flags = compute_pattern_flags(cur, None)
    ids = [f["id"] for f in flags]
    assert "military_chatter_elevated" in ids


def test_military_chatter_spike_vs_previous():
    prev = _base_result(
        news={"articles": [{"title": "Weather", "description": ""}] * 8},
        sigint={"conflict_reports": [], "aircraft": [], "ships": []},
        socmint={"top_signals": ["routine"] * 4},
    )
    cur = _base_result(
        escalation_score=52.0,
        news={
            "articles": [
                {"title": "Ballistic missile launch military strike retaliation", "description": "nato border"},
            ]
            * 30
        },
        sigint={
            "conflict_reports": [{"title": "Pentagon tracks warship deployment"}] * 8,
            "aircraft": [],
            "ships": [],
        },
        socmint={"top_signals": ["drone strike combat"] * 10},
    )
    flags = compute_pattern_flags(cur, prev)
    ids = [f["id"] for f in flags]
    assert "military_chatter_spike" in ids


def test_escalation_jump():
    prev = _base_result(escalation_score=40.0)
    cur = _base_result(escalation_score=58.0)
    flags = compute_pattern_flags(cur, prev)
    assert any(f["id"] == "escalation_jump" for f in flags)
