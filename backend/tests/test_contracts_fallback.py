"""Unit tests for agents.contracts.get_agent_fallback."""

import pytest

from agents.contracts import AGENT_RESULT_TYPES, get_agent_fallback
from agents.registry import DEFAULT_AGENTS


@pytest.mark.parametrize("agent_name", [d.name for d in DEFAULT_AGENTS])
def test_get_agent_fallback_returns_dict_with_expected_keys(agent_name):
    """Every registered agent has a fallback dict with at least conflict, summary, score-like key."""
    fallback = get_agent_fallback(agent_name)
    assert isinstance(fallback, dict)
    assert "conflict" in fallback or "summary" in fallback
    # Each contract extends BaseAgentResult and has a score field
    model_cls = AGENT_RESULT_TYPES.get(agent_name)
    assert model_cls is not None
    instance = model_cls()
    expected_keys = set(instance.model_dump().keys())
    assert expected_keys.issubset(set(fallback.keys())), f"Missing keys for {agent_name}"


def test_get_agent_fallback_unknown_returns_empty():
    """Unknown agent name returns empty dict."""
    assert get_agent_fallback("unknown_agent") == {}
