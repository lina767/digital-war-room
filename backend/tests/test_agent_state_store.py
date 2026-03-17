"""
Tests for AgentStateStore: get/set results, content hashes, circuit breaker persistence.
"""

from agents.agent_state_store import get_agent_state_store
from agents.base import CircuitBreakerState


class TestResultStorage:
    def test_get_returns_none_when_empty(self, state_store):
        assert state_store.get_result("Iran", "sigint") is None

    def test_set_and_get(self, state_store):
        state_store.set_result("Iran", "sigint", {"score": 65}, 1000.0)
        entry = state_store.get_result("Iran", "sigint")
        assert entry is not None
        result, ts = entry
        assert result["score"] == 65
        assert ts == 1000.0

    def test_overwrite(self, state_store):
        state_store.set_result("Iran", "sigint", {"score": 40}, 1000.0)
        state_store.set_result("Iran", "sigint", {"score": 65}, 2000.0)
        result, ts = state_store.get_result("Iran", "sigint")
        assert result["score"] == 65
        assert ts == 2000.0

    def test_isolation_per_conflict(self, state_store):
        state_store.set_result("Iran", "sigint", {"score": 40}, 1000.0)
        state_store.set_result("Taiwan", "sigint", {"score": 80}, 1000.0)
        r1, _ = state_store.get_result("Iran", "sigint")
        r2, _ = state_store.get_result("Taiwan", "sigint")
        assert r1["score"] == 40
        assert r2["score"] == 80

    def test_isolation_per_agent(self, state_store):
        state_store.set_result("Iran", "sigint", {"score": 40}, 1000.0)
        state_store.set_result("Iran", "news", {"score": 60}, 1000.0)
        r1, _ = state_store.get_result("Iran", "sigint")
        r2, _ = state_store.get_result("Iran", "news")
        assert r1["score"] == 40
        assert r2["score"] == 60


class TestContentHash:
    def test_get_returns_none_when_empty(self, state_store):
        assert state_store.get_content_hash("Iran", "sigint") is None

    def test_set_and_get(self, state_store):
        state_store.set_content_hash("Iran", "sigint", "abc123")
        assert state_store.get_content_hash("Iran", "sigint") == "abc123"

    def test_has_changed_true_when_different(self, state_store):
        state_store.set_content_hash("Iran", "sigint", "abc123")
        assert state_store.has_changed("Iran", "sigint", "def456") is True

    def test_has_changed_false_when_same(self, state_store):
        state_store.set_content_hash("Iran", "sigint", "abc123")
        assert state_store.has_changed("Iran", "sigint", "abc123") is False

    def test_has_changed_true_when_no_previous(self, state_store):
        assert state_store.has_changed("Iran", "sigint", "abc123") is True


class TestCircuitBreaker:
    def test_get_returns_default_when_empty(self, state_store):
        cb = state_store.get_circuit_breaker("sigint")
        assert isinstance(cb, CircuitBreakerState)
        assert cb.consecutive_failures == 0
        assert cb.is_open is False

    def test_set_and_get(self, state_store):
        cb = CircuitBreakerState(consecutive_failures=3, is_open=True)
        state_store.set_circuit_breaker("sigint", cb)
        loaded = state_store.get_circuit_breaker("sigint")
        assert loaded.consecutive_failures == 3
        assert loaded.is_open is True

    def test_circuit_breaker_is_global_not_per_conflict(self, state_store):
        cb = CircuitBreakerState(consecutive_failures=5, is_open=True)
        state_store.set_circuit_breaker("sigint", cb)
        loaded = state_store.get_circuit_breaker("sigint")
        assert loaded.is_open is True


class TestClear:
    def test_clear_all(self, state_store):
        state_store.set_result("Iran", "sigint", {"x": 1}, 1.0)
        state_store.set_content_hash("Iran", "sigint", "h1")
        state_store.set_circuit_breaker("sigint", CircuitBreakerState(is_open=True))
        state_store.clear()
        assert state_store.get_result("Iran", "sigint") is None
        assert state_store.get_content_hash("Iran", "sigint") is None
        assert state_store.get_circuit_breaker("sigint").is_open is False

    def test_clear_specific_conflict(self, state_store):
        state_store.set_result("Iran", "sigint", {"x": 1}, 1.0)
        state_store.set_result("Taiwan", "sigint", {"x": 2}, 1.0)
        state_store.clear(conflict="Iran")
        assert state_store.get_result("Iran", "sigint") is None
        assert state_store.get_result("Taiwan", "sigint") is not None


class TestSingleton:
    def test_get_agent_state_store_returns_same_instance(self):
        s1 = get_agent_state_store()
        s2 = get_agent_state_store()
        assert s1 is s2
