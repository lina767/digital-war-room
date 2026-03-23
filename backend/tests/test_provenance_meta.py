"""Tests for OSINT provenance fields on agent _meta and CEO response."""

import uuid

import pytest

from agents.utils import (
    ProcessingStep,
    SourceResult,
    build_agent_meta,
    cap_reference_urls,
    enrich_source_results_provenance,
    reset_analysis_run_id,
    set_analysis_run_id,
)


def test_cap_reference_urls_dedupes_and_caps() -> None:
    u = ["https://a.com/1", "https://a.com/1", "https://b.com"]
    assert cap_reference_urls(u, max_n=2) == ["https://a.com/1", "https://b.com"]


def test_build_agent_meta_includes_processing_steps_and_run_id() -> None:
    token = set_analysis_run_id(str(uuid.uuid4()))
    try:
        rid = str(uuid.uuid4())
        sources = [
            SourceResult(name="NewsAPI", status="ok", fetched_at="2025-01-01T00:00:00+00:00", record_count=2),
        ]
        steps = [ProcessingStep(step="fusion", at="2025-01-01T00:00:01+00:00", detail="test")]
        meta = build_agent_meta(
            "news",
            "2025-01-01T00:00:00+00:00",
            100,
            sources,
            has_any_data=True,
            processing_steps=steps,
            analysis_run_id=rid,
        )
        assert meta["analysis_run_id"] == rid
        assert len(meta["processing_steps"]) == 1
        assert meta["processing_steps"][0]["step"] == "fusion"
        assert meta["agent"] == "news"
        src0 = meta["sources"][0]
        assert "reference_urls" in src0
        assert any("newsapi.org" in u for u in (src0.get("reference_urls") or []))
    finally:
        reset_analysis_run_id(token)


def test_enrich_source_results_finint() -> None:
    sr = SourceResult(name="Alpha Vantage (Brent)", status="ok", fetched_at="2025-01-01T00:00:00+00:00")
    out = enrich_source_results_provenance("finint", [sr])
    assert out[0].reference_urls
    assert out[0].endpoint_kind == "rest"


def test_ceo_synthesize_includes_provenance_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule-based CEO path returns analysis_run_id and provenance_index."""
    monkeypatch.setenv("USE_RULE_BASED_SUPERVISOR", "1")
    token = set_analysis_run_id(str(uuid.uuid4()))
    try:
        from agents.ceo import _ceo_synthesize
        from agents.dag_scheduler import ResultStore

        store = ResultStore(cycle_id="c1", conflict="Iran")
        fin_meta = build_agent_meta(
            "finint",
            "2025-01-01T00:00:00+00:00",
            50,
            [
                SourceResult(
                    name="Alpha Vantage (Brent)",
                    status="ok",
                    fetched_at="2025-01-01T00:00:00+00:00",
                )
            ],
            has_any_data=True,
        )
        store.set("finint", {"escalation_score": 40.0, "_meta": fin_meta})
        store.set("sigint", {"sigint_score": 30.0, "_meta": {"data_confidence": "estimated", "sources": []}})
        store.set("news", {"news_score": 50.0, "_meta": {"data_confidence": "estimated", "sources": []}})
        store.set("geoint", {"geoint_score": 20.0, "_meta": {"data_confidence": "estimated", "sources": []}})
        store.set("satintel", {"satintel_score": 10.0})
        store.set("socmint", {"socmint_score": 10.0})
        store.set("techint", {"techint_score": 10.0})
        store.set("cyber", {"cyber_score": 10.0})
        store.set("energy", {"energy_score": 10.0})
        store.set("protest", {"protest_score": 10.0})
        store.set("diplo", {"diplo_score": 10.0})
        store.set("proximity", {"proximity_score": 10.0})
        store.set("narrative", {})
        store.set("chokepoint", {"chokepoint_score": 10.0})
        store.set("compliance_build", {"compliance": {}, "alerts": []})
        store.set("acled_refs", [])

        out = _ceo_synthesize("Iran", [], store)  # type: ignore[arg-type]
        assert out.get("analysis_run_id")
        uuid.UUID(out["analysis_run_id"])
        idx = out.get("provenance_index") or []
        assert isinstance(idx, list) and len(idx) >= 1
        fin = next((p for p in idx if p.get("agent") == "finint"), None)
        assert fin is not None
        assert fin.get("sources_total", 0) >= 1
    finally:
        reset_analysis_run_id(token)


def test_build_provenance_snapshot_structure() -> None:
    from services.analysis_audit_store import build_provenance_snapshot

    result = {
        "analysis_run_id": str(uuid.uuid4()),
        "provenance_index": [{"agent": "finint"}],
        "finint": {"_meta": {"agent": "finint", "sources": []}},
        "news": {"articles": []},
    }
    snap = build_provenance_snapshot(result)
    assert snap["analysis_run_id"] == result["analysis_run_id"]
    assert "finint" in snap["agents"]
    assert "news" not in snap["agents"]
