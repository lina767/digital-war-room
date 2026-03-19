"""Tests for main app endpoints (health, root)."""

import pytest
from fastapi.testclient import TestClient

# Import app after env is loaded so lifespan and limiter are configured
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "conflict-backend"
