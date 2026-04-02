import asyncio

from agents.cross_agent_corroboration import apply_cross_agent_corroboration
from agents.finding_signal_gate import FindingCandidate, score_and_gate_findings


def test_cross_agent_corroboration_applies_bonus_and_penalty():
    candidates = [
        FindingCandidate(
            text="NEWS (NEGATIVE) – Explosion near Basra refinery reported by Reuters",
            sources=[{"name": "Reuters", "url": "https://www.reuters.com/world/middle-east/basra-event"}],
            agents=["news"],
            metadata={},
        ),
        FindingCandidate(
            text="PROTEST (GDELT) – Explosion near Basra refinery triggers unrest claims",
            sources=[{"name": "GDELT", "url": "https://gdeltproject.org/article/123", "kind": "gdelt"}],
            agents=["protest"],
            metadata={},
        ),
        FindingCandidate(
            text="PROTEST (GDELT) – Isolated rally mention in one city district",
            sources=[{"name": "GDELT", "url": "https://gdeltproject.org/article/999", "kind": "gdelt"}],
            agents=["protest"],
            metadata={},
        ),
    ]

    updated, meta = apply_cross_agent_corroboration(candidates)
    assert len(updated) == 3
    assert meta["events"] >= 2
    assert meta["single_source_downgrades"] >= 1

    first_adj = float(updated[0].metadata.get("corroboration_adjustment") or 0.0)
    second_adj = float(updated[1].metadata.get("corroboration_adjustment") or 0.0)
    third_adj = float(updated[2].metadata.get("corroboration_adjustment") or 0.0)

    assert first_adj > 0.0
    assert second_adj > 0.0
    assert third_adj < 0.0


def test_signal_gate_uses_corroboration_adjustment():
    candidates = [
        FindingCandidate(
            text="NEWS – Confirmed event in port city with actors and timeframe",
            sources=[{"name": "Reuters", "url": "https://www.reuters.com/a"}],
            agents=["news"],
            metadata={"corroboration_adjustment": 0.2},
        ),
        FindingCandidate(
            text="PROTEST (GDELT) – Single-source mention only",
            sources=[{"name": "GDELT", "url": "https://gdeltproject.org/x", "kind": "gdelt"}],
            agents=["protest"],
            metadata={"corroboration_adjustment": -0.2},
        ),
    ]

    result = asyncio.run(
        score_and_gate_findings(
            candidates=candidates,
            conflict="Iraq",
            threshold=0.6,
            max_llm=0,
        )
    )

    accepted = result.get("accepted") or []
    archived = result.get("archived") or []
    assert accepted and archived
    assert accepted[0]["adjustment"] > 0
    assert archived[0]["adjustment"] < 0


def test_corroboration_requires_anchor_for_medium_similarity():
    # Similar topic words but different place/time -> should not cluster.
    candidates = [
        FindingCandidate(
            text="NEWS – Explosion reported near Basra refinery today",
            sources=[{"name": "Reuters", "url": "https://www.reuters.com/a"}],
            agents=["news"],
            metadata={},
        ),
        FindingCandidate(
            text="PROTEST (GDELT) – Explosion claims discussed in Khartoum this week",
            sources=[{"name": "GDELT", "url": "https://gdeltproject.org/b", "kind": "gdelt"}],
            agents=["protest"],
            metadata={},
        ),
    ]

    updated, meta = apply_cross_agent_corroboration(candidates)
    assert meta["events"] == 2
    for row in updated:
        evt = row.metadata.get("corroboration_event") or {}
        assert int(evt.get("cluster_size") or 0) == 1
