"""Tests for API rate limiting (slowapi) on /api/analyze and other limited routes."""

import time

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_analyze_rate_limit_returns_429_after_limit(client: TestClient):
    """POST /api/analyze is limited to 10/minute; 11th request returns 429."""
    # Use context manager so lifespan runs and state_service is set
    with client:
        state = getattr(client.app.state, "state_service", None)
        if state is None:
            from services.state_service import StateService
            client.app.state.state_service = StateService()
            state = client.app.state.state_service
        state.set_cache(
            "Iran",
            {"conflict": "Iran", "escalation_score": 50.0, "summary": "cached"},
            time.time(),
        )
        # First 10 succeed
        for _ in range(10):
            r = client.post("/api/analyze", json={"conflict": "Iran"})
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        # 11th request is rate limited (429)
        r = client.post("/api/analyze", json={"conflict": "Iran"})
        assert r.status_code == 429, f"Expected 429, got {r.status_code}"
        body = r.json() if r.content else {}
        detail = (body.get("detail") or body.get("message") or "").lower()
        if detail:
            assert "rate" in detail or "limit" in detail or "exceeded" in detail
