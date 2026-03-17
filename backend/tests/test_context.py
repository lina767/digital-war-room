"""Unit tests for agents.context.build_context_from_results."""

from agents.context import build_context_from_results


def test_build_context_empty_wave1():
    """Empty wave1_results yields empty but valid context."""
    ctx = build_context_from_results({})
    assert ctx.peer_summaries == {}
    assert ctx.focus_regions == []
    assert ctx.key_findings_so_far == []
    assert ctx.escalation_signals == []


def test_build_context_peer_summaries():
    """Wave1 results with summaries populate peer_summaries (truncated to 500)."""
    wave1 = {
        "finint": {"summary": "Brent up 2%."},
        "sigint": {"summary": "A" * 600},
        "news": {"summary": ""},
    }
    ctx = build_context_from_results(wave1)
    assert ctx.peer_summaries["finint"] == "Brent up 2%."
    assert len(ctx.peer_summaries["sigint"]) == 500
    assert "news" not in ctx.peer_summaries


def test_build_context_focus_regions_from_sigint():
    """SIGINT aircraft/ships with valid lat/lon become focus_regions."""
    wave1 = {
        "sigint": {
            "aircraft": [
                {"lat": 27.1, "lon": 53.2, "region": "Gulf"},
                {"lat": "invalid", "lon": 53},  # skipped
                {"error": "timeout"},  # skipped
            ],
            "ships": [{"lat": 30.0, "lon": 50.0}],
        },
    }
    ctx = build_context_from_results(wave1)
    assert len(ctx.focus_regions) >= 2
    regions = [r["region"] for r in ctx.focus_regions]
    assert "Gulf" in regions
    assert "ship" in regions


def test_build_context_bad_coords_no_crash():
    """Non-numeric lat/lon do not crash; invalid items are skipped."""
    wave1 = {
        "sigint": {
            "aircraft": [
                {"lat": None, "lon": 53},
                {"lat": 27, "lon": "n/a"},
                {"lat": 27, "lon": 53},  # valid
            ],
        },
    }
    ctx = build_context_from_results(wave1)
    assert len(ctx.focus_regions) == 1
    assert ctx.focus_regions[0]["lat"] == 27 and ctx.focus_regions[0]["lon"] == 53


def test_build_context_escalation_signals_from_news():
    """News articles with escalation_headline populate escalation_signals."""
    wave1 = {
        "news": {
            "articles": [
                {"title": "Tensions rise", "escalation_headline": True},
                {"title": "Normal", "escalation_headline": False},
            ],
        },
    }
    ctx = build_context_from_results(wave1)
    assert len(ctx.escalation_signals) == 1
    assert "Tensions rise" in ctx.escalation_signals[0]
