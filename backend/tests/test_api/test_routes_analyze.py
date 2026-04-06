"""FastAPI endpoint tests for analyze routes."""

from collections import deque

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_analyze import router as analyze_router
from middleware.rate_limit import limiter
from services.state_service import StateService


@pytest.fixture
def client():
    class DummyWsManager:
        async def broadcast(self, _data):
            return None

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(analyze_router, prefix="/api")
    app.state.state_service = StateService()
    app.state.analysis_cache = {}
    app.state.analysis_last_error = {}
    app.state.escalation_timeline_history = {}
    app.state.agent_status_last = {}
    app.state.analysis_run_history = deque(maxlen=50)
    app.state.ws_manager = DummyWsManager()
    return TestClient(app)


def test_analyze_status_without_cache(client: TestClient):
    response = client.get("/api/analyze/status", params={"conflict": "Iran"})
    assert response.status_code == 200
    assert response.json() == {"cached": False, "conflict": "Iran", "running": False}


def test_analyze_latest_returns_404_without_cache(client: TestClient):
    response = client.get("/api/analyze/latest", params={"conflict": "Iran"})
    assert response.status_code == 404
    assert response.json()["error"] == "no_cached_analysis"


def test_analyze_latest_returns_cached_result(client: TestClient):
    client.app.state.state_service.set_cache(
        "Iran",
        {"conflict": "Iran", "escalation_score": 62.5, "summary": "cached"},
        1710840000.0,
    )

    response = client.get("/api/analyze/latest", params={"conflict": "Iran"})
    assert response.status_code == 200
    body = response.json()
    assert body["conflict"] == "Iran"
    assert body["escalation_score"] == 62.5
    assert body["summary"] == "cached"


def test_agents_monitoring_returns_shape(client: TestClient):
    response = client.get("/api/agents/monitoring")
    assert response.status_code == 200
    body = response.json()
    assert "fallback" in body
    assert "errors" in body
    assert "cost" in body
    assert "month_budget_usd" in body["cost"]
    assert "daily" in body["cost"]
    assert "google_trend_serp" in body


def test_google_trend_snapshot_without_serpapi_key(client: TestClient, monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    response = client.post("/api/agents/google-trend-snapshot", json={"conflict": "Iran"})
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is False
    assert body.get("error") == "missing SERPAPI_KEY"
    mon = client.get("/api/agents/monitoring").json()
    assert mon.get("google_trend_serp", {}).get("error") == "missing SERPAPI_KEY"


def test_refresh_returns_already_running_when_inflight(client: TestClient):
    # Same scope format as production: "<tenant_id>\\n<conflict>"
    client.app.state.analysis_inflight = {"00000000-0000-4000-8000-000000000001\nIran": 1.0}
    response = client.post("/api/analyze/refresh", params={"conflict": "Iran"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "already_running"
    assert body["conflict"] == "Iran"
