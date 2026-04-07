"""FastAPI endpoint tests for chat MVP routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chat import (
    _build_context_for_type,
    _collect_sources,
    _detect_question_type,
    _fallback_agent_sources,
    _question_context_plan,
    router as chat_router,
)
from middleware.rate_limit import limiter
from services.state_service import StateService


def _client() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.state.state_service = StateService()
    app.include_router(chat_router, prefix="/api")
    return TestClient(app)


def test_chat_ask_returns_fallback_without_cache():
    client = _client()
    r = client.post("/api/chat/ask", json={"question": "What changed since yesterday?", "conflict": "Iran"})
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_used"] is True
    assert body["answer"] == "No reliable answer available."
    assert body["confidence_score"] == 0
    assert body["sources"] == []


def test_chat_ask_returns_structured_answer(monkeypatch):
    client = _client()
    client.app.state.state_service.set_cache(
        "Iran",
        {
            "conflict": "Iran",
            "summary": "Escalation pressure remains elevated.",
            "key_findings": ["Air activity increased near key corridor."],
            "news": {"articles": [{"url": "https://example.com/report"}]},
        },
        at=1710840000.0,
    )

    async def _fake_analyst_summary(**_kwargs):
        return (
            '{"answer":"Escalation risk is elevated with increased air activity.",'
            '"confidence_score":0.82,"sources":["https://example.com/report"]}'
        )

    monkeypatch.setattr("api.routes_chat.analyst_summary", _fake_analyst_summary)
    r = client.post("/api/chat/ask", json={"question": "What is the current risk level?", "conflict": "Iran"})
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_used"] is False
    assert body["confidence_score"] >= 0.8
    assert body["sources"] == ["https://example.com/report"]


def test_chat_feedback_persists(monkeypatch):
    client = _client()

    async def _fake_resolve_chat_response(**_kwargs):
        return {
            "response_id": "f3cb6497-57c0-45e1-8f66-f4f68bb13755",
            "conflict": "Iran",
            "question_type": "changes_since_yesterday",
            "question": "What changed since yesterday?",
            "answer": "No major military posture shift is visible.",
            "confidence_score": 0.7,
            "sources": ["https://example.com/report"],
            "fallback_used": False,
        }

    async def _fake_persist(_event):
        return {"stored": True, "storage": "memory"}

    monkeypatch.setattr("api.routes_chat.resolve_chat_response", _fake_resolve_chat_response)
    monkeypatch.setattr("api.routes_chat.persist_chat_feedback", _fake_persist)
    r = client.post(
        "/api/chat/feedback",
        json={
            "response_id": "f3cb6497-57c0-45e1-8f66-f4f68bb13755",
            "helpful": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_feedback_unknown_response_returns_404(monkeypatch):
    client = _client()

    async def _fake_resolve_chat_response(**_kwargs):
        return None

    monkeypatch.setattr("api.routes_chat.resolve_chat_response", _fake_resolve_chat_response)
    r = client.post(
        "/api/chat/feedback",
        json={
            "response_id": "00000000-0000-4000-8000-000000000099",
            "helpful": True,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["status"] == "not_found"


def test_question_context_plan_risk_and_outlook():
    analysis = {"finint": {"summary": "x"}}
    risk = _question_context_plan("risk_assessment", analysis)
    assert risk["primary"] == ["compliance", "finint", "cyber"]
    assert risk["secondary"] == ["narrative", "proximity"]
    outlook = _question_context_plan("next_24h_outlook", analysis)
    assert outlook["primary"] == ["scenarios", "cyber", "socmint", "diplo"]
    assert outlook["secondary"] == ["narrative", "finint", "chokepoint"]


def test_build_context_risk_assessment_includes_compliance_finint_cyber():
    analysis = {
        "conflict": "Test",
        "summary": "Top summary.",
        "escalation_score": 50.0,
        "threat_level": "HIGH",
        "key_findings": [],
        "compliance": {"risk_score": {"level": "Elevated", "drivers": [{"factor": "X", "detail": "Y"}]}},
        "finint": {"summary": "Market stress."},
        "cyber": {
            "summary": "Cyber overview.",
            "greynoise_scan_context": [{"ip": "1.1.1.1", "classification": "benign", "last_seen": "t0"}],
            "cisa_kev": [{"cve": "CVE-9999"}],
        },
        "narrative": {"synthesis_text": "Cross-stream story."},
        "proximity": {"evidence": [], "summary": "prox"},
    }
    ctx = _build_context_for_type(analysis, "Test", "risk_assessment")
    assert "COMPLIANCE risk level" in ctx
    assert "FININT summary" in ctx
    assert "CYBER summary" in ctx
    assert "CVE-9999" in ctx
    assert "synthesis_text" in ctx


def test_build_context_next_24h_uses_greynoise_focus_and_streams():
    analysis = {
        "conflict": "Test",
        "summary": "S",
        "escalation_score": 0.0,
        "threat_level": "LOW",
        "key_findings": [],
        "scenarios": [{"description": "Supply shock", "probability": 0.2}],
        "cyber": {
            "summary": "Cyber overview.",
            "greynoise_scan_context": [{"ip": "9.9.9.9", "classification": "unknown", "last_seen": "t1"}],
            "cisa_kev": [{"cve": "CVE-1"}],
        },
        "socmint": {"summary": "Social signals.", "top_signals": []},
        "diplo": {"summary": "Diplomatic track."},
    }
    ctx = _build_context_for_type(analysis, "Test", "next_24h_outlook")
    assert "SCENARIOS:" in ctx
    assert "CYBER GREYNOISE (focused):" in ctx
    assert "SOCMINT summary" in ctx
    assert "DIPLO summary" in ctx
    assert "CVE-1" not in ctx


def test_fallback_agent_sources_aligned_with_matrix():
    analysis = {
        "compliance": {"risk_score": {}},
        "finint": {"summary": "f"},
        "cyber": {"summary": "c"},
        "scenarios": [{"description": "x"}],
        "socmint": {"summary": "s"},
        "diplo": {"summary": "d"},
    }
    risk = _fallback_agent_sources("risk_assessment", analysis)
    assert "COMPLIANCE risk model" in risk
    assert "FININT indicators" in risk
    assert "CYBER indicators" in risk
    out = _fallback_agent_sources("next_24h_outlook", analysis)
    assert "SCENARIO projection" in out
    assert "CYBER GREYNOISE focus" in out
    assert "SOCMINT civil-unrest proxy" in out
    assert "DIPLO sanctions track" in out


def test_chat_feedback_summary(monkeypatch):
    client = _client()

    async def _fake_summary(**_kwargs):
        return {
            "storage": "memory",
            "total_feedback": 3,
            "helpful_total": 2,
            "helpful_rate": 0.667,
            "trend_days": [{"day": "2026-04-07", "count": 3, "helpful_count": 2, "helpful_rate": 0.667}],
            "by_question_type": [
                {
                    "question_type": "risk_assessment",
                    "count": 2,
                    "helpful_count": 1,
                    "helpful_rate": 0.5,
                    "avg_confidence": 0.7,
                    "fallback_count": 1,
                    "fallback_rate": 0.5,
                }
            ],
            "fallback_total": 1,
            "fallback_rate": 0.333,
        }

    monkeypatch.setattr("api.routes_chat.get_chat_feedback_summary", _fake_summary)
    r = client.get("/api/chat/feedback/summary", params={"days": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["days"] == 14
    assert body["total_feedback"] == 3
    assert body["trend_days"][0]["day"] == "2026-04-07"
    assert body["fallback_total"] == 1


def test_detect_question_type_supports_german_keywords():
    assert _detect_question_type("Was hat sich seit gestern geaendert?") == "changes_since_yesterday"
    assert _detect_question_type("Wie hoch ist das Eskalationsrisiko?") == "risk_assessment"
    assert _detect_question_type("Gib mir einen Ausblick fuer die naechsten 24 Stunden") == "next_24h_outlook"
    assert _detect_question_type("Welche Quellen hast du dafuer?") == "source_check"


def test_collect_sources_keeps_only_http_urls_and_dedupes_case_insensitive():
    analysis = {
        "news": {
            "articles": [
                {"url": "https://Example.com/report"},
                {"url": "HTTPS://example.com/report"},
                {"url": "ftp://example.com/not-allowed"},
            ]
        },
        "sigint": {
            "_meta": {
                "sources": [
                    {"reference_urls": ["https://example.com/report", "mailto:test@example.com"]},
                ]
            }
        },
    }
    assert _collect_sources(analysis) == ["https://Example.com/report"]


def test_chat_ask_returns_low_confidence_partial_answer_instead_of_hard_fallback(monkeypatch):
    client = _client()
    client.app.state.state_service.set_cache(
        "Iran",
        {
            "conflict": "Iran",
            "summary": "Signals are mixed and still evolving.",
            "key_findings": ["Sparse source coverage in the last cycle."],
            "news": {"articles": [{"url": "https://example.com/report"}]},
        },
        at=1710840000.0,
    )

    async def _fake_analyst_summary(**_kwargs):
        return (
            '{"answer":"Early indicators point to elevated uncertainty.",'
            '"confidence_score":0.22,"sources":[]}'
        )

    monkeypatch.setattr("api.routes_chat.analyst_summary", _fake_analyst_summary)
    r = client.post("/api/chat/ask", json={"question": "Risk right now?", "conflict": "Iran"})
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_used"] is False
    assert body["confidence_score"] == 0.22
    assert "Evidence is currently limited in cache" in body["answer"]
