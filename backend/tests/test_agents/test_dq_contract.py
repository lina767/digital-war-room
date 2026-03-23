"""Tests for dq_contract sync and AgentQualityFields."""

from agents.dq_contract import AgentQualityFields, sync_agent_quality_from_meta


def test_sync_agent_quality_from_meta_fills_from_meta():
    agent = {
        "_meta": {
            "confidence": {"level": "high"},
            "data_freshness": "live",
            "fallback_used": False,
            "sources": [
                {"name": "NewsAPI", "status": "ok", "reference_urls": ["https://newsapi.org/docs"]},
                {"name": "RSS", "status": "ok", "reference_urls": []},
            ],
        }
    }
    sync_agent_quality_from_meta(agent)
    assert agent["source_count"] == 2
    assert agent["dq_confidence"] > 0
    assert agent["data_freshness"] == "live"
    assert "https://newsapi.org/docs" in agent["provenance_refs"]


def test_agent_quality_fields_model_defaults():
    q = AgentQualityFields()
    assert q.dq_confidence == 0.0
    assert q.data_freshness == "unavailable"
