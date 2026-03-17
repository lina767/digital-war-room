"""
Shared pytest fixtures for the multi-agent hierarchy test suite.
"""
import pytest

from agents.agent_state_store import AgentStateStore
from agents.contracts import EnergyResult


@pytest.fixture
def state_store():
    """Fresh AgentStateStore per test."""
    return AgentStateStore()


@pytest.fixture
def energy_fallback():
    """Default EnergyResult for fallback testing."""
    return EnergyResult(conflict="test", energy_score=30.0, summary="fallback")


@pytest.fixture
def mock_energy_result():
    """Realistic EnergyResult for success-path testing."""
    return EnergyResult(
        conflict="Iran",
        energy_score=42.5,
        commodities=[{"symbol": "BRENT", "price": "78.50", "change_pct": "+1.2%"}],
        food_commodities=[{"symbol": "WHEAT", "price": "5.80"}],
        food_security_risk=35.0,
        summary="Brent +1.2%, wheat stable.",
    )
