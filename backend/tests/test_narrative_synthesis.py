"""Tests for cross-stream narrative synthesis (fallback paths)."""

from agents.narrative_synthesis import _fallback_narrative


def test_fallback_narrative_with_scores():
    text = _fallback_narrative(
        {
            "conflict": "Iran",
            "agent_scores": {"finint": 80.0, "sigint": 40.0, "chokepoint": 70.0},
            "finint": {"summary": "Brent moved sharply."},
        }
    )
    assert "Iran" in text
    assert "finint" in text.lower() or "80" in text
