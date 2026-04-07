"""FastAPI endpoint tests for chat MVP routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chat import router as chat_router
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
    assert body["answer"] == "Keine belastbare Antwort"
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

    async def _fake_persist(_event):
        return {"stored": True, "storage": "memory"}

    monkeypatch.setattr("api.routes_chat.persist_chat_feedback", _fake_persist)
    r = client.post(
        "/api/chat/feedback",
        json={
            "response_id": "f3cb6497-57c0-45e1-8f66-f4f68bb13755",
            "conflict": "Iran",
            "question": "What changed since yesterday?",
            "question_type": "changes_since_yesterday",
            "answer": "No major military posture shift is visible.",
            "confidence_score": 0.7,
            "sources": ["https://example.com/report"],
            "helpful": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


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
                }
            ],
        }

    monkeypatch.setattr("api.routes_chat.get_chat_feedback_summary", _fake_summary)
    r = client.get("/api/chat/feedback/summary", params={"days": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["days"] == 14
    assert body["total_feedback"] == 3
    assert body["trend_days"][0]["day"] == "2026-04-07"
