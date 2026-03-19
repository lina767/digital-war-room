"""FastAPI endpoint tests for analyze routes."""

from collections import deque

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_analyze import router as analyze_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(analyze_router, prefix="/api")
    app.state.analysis_cache = {}
    app.state.analysis_last_error = {}
    app.state.escalation_timeline_history = {}
    app.state.agent_status_last = {}
    app.state.analysis_run_history = deque(maxlen=50)
    return TestClient(app)


def test_analyze_status_without_cache(client: TestClient):
    response = client.get("/api/analyze/status", params={"conflict": "Iran"})
    assert response.status_code == 200
    assert response.json() == {"cached": False, "conflict": "Iran"}


def test_analyze_latest_returns_404_without_cache(client: TestClient):
    response = client.get("/api/analyze/latest", params={"conflict": "Iran"})
    assert response.status_code == 404
    assert response.json()["error"] == "no_cached_analysis"


def test_analyze_latest_returns_cached_result(client: TestClient):
    client.app.state.analysis_cache["Iran"] = {
        "result": {"conflict": "Iran", "escalation_score": 62.5, "summary": "cached"},
        "at": 1710840000.0,
    }

    response = client.get("/api/analyze/latest", params={"conflict": "Iran"})
    assert response.status_code == 200
    body = response.json()
    assert body["conflict"] == "Iran"
    assert body["escalation_score"] == 62.5
    assert body["summary"] == "cached"
