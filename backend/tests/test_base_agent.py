"""
Tests for BaseAgent: run_safe, circuit breaker, content hash, fallback, timeout.
"""

import time

from agents.agent_state_store import AgentStateStore
from agents.base import AgentResult, BaseAgent, BaseAgentResult, CircuitBreakerState
from agents.contracts import EnergyResult

# -- Test agent implementations (also available via conftest fixtures) ------


class SuccessAgent(BaseAgent[EnergyResult]):
    name = "test_success"
    timeout = 5.0
    result_type = EnergyResult

    def __init__(self, result: EnergyResult | None = None):
        super().__init__()
        self._result = result or EnergyResult(conflict="test", energy_score=50.0, summary="ok")

    def run(self, conflict: str) -> EnergyResult:
        return self._result


class FailingAgent(BaseAgent[EnergyResult]):
    name = "test_fail"
    timeout = 5.0
    result_type = EnergyResult

    def __init__(self):
        super().__init__()

    def run(self, conflict: str) -> EnergyResult:
        raise RuntimeError("intentional test failure")

    def get_fallback(self, conflict: str) -> EnergyResult:
        return EnergyResult(conflict=conflict, energy_score=0.0, summary="fallback")


class SlowAgent(BaseAgent[EnergyResult]):
    name = "test_slow"
    timeout = 0.5
    result_type = EnergyResult

    def __init__(self):
        super().__init__()

    def run(self, conflict: str) -> EnergyResult:
        time.sleep(5)
        return EnergyResult(conflict=conflict, energy_score=99.0)

    def get_fallback(self, conflict: str) -> EnergyResult:
        return EnergyResult(conflict=conflict, energy_score=0.0, summary="timeout fallback")


class TestRunSafeSuccess:
    def test_returns_agent_result(self):
        agent = SuccessAgent()
        ar = agent.run_safe("Iran")
        assert isinstance(ar, AgentResult)
        assert ar.is_fallback is False
        assert ar.error is None

    def test_result_data_is_typed(self):
        agent = SuccessAgent()
        ar = agent.run_safe("Iran")
        assert isinstance(ar.data, EnergyResult)
        assert ar.data.energy_score == 50.0

    def test_content_hash_is_nonempty(self):
        agent = SuccessAgent()
        ar = agent.run_safe("Iran")
        assert ar.content_hash
        assert len(ar.content_hash) == 16

    def test_metrics_latency(self):
        agent = SuccessAgent()
        ar = agent.run_safe("Iran")
        assert ar.metrics.latency_ms >= 0

    def test_deterministic_hash(self):
        result = EnergyResult(conflict="Iran", energy_score=42.0)
        a1 = SuccessAgent(result)
        a2 = SuccessAgent(result)
        h1 = a1.run_safe("Iran").content_hash
        h2 = a2.run_safe("Iran").content_hash
        assert h1 == h2

    def test_different_data_different_hash(self):
        a1 = SuccessAgent(EnergyResult(conflict="Iran", energy_score=42.0))
        a2 = SuccessAgent(EnergyResult(conflict="Iran", energy_score=99.0))
        h1 = a1.run_safe("Iran").content_hash
        h2 = a2.run_safe("Iran").content_hash
        assert h1 != h2


class TestRunSafeFailure:
    def test_failure_returns_fallback(self):
        agent = FailingAgent()
        ar = agent.run_safe("Iran")
        assert ar.is_fallback is True
        assert ar.error is not None
        assert "intentional" in ar.error

    def test_failure_data_is_fallback(self):
        agent = FailingAgent()
        ar = agent.run_safe("Iran")
        assert isinstance(ar.data, EnergyResult)
        assert ar.data.summary == "fallback"

    def test_failure_still_has_hash(self):
        agent = FailingAgent()
        ar = agent.run_safe("Iran")
        assert ar.content_hash


class TestTimeout:
    def test_timeout_returns_fallback(self):
        agent = SlowAgent()
        ar = agent.run_safe("Iran")
        assert ar.is_fallback is True
        assert "timeout" in ar.error.lower()


class TestCircuitBreaker:
    def test_opens_after_3_failures(self):
        agent = FailingAgent()
        for _ in range(3):
            agent.run_safe("Iran")
        assert agent._circuit_breaker.is_open is True

    def test_skips_while_open(self):
        agent = FailingAgent()
        for _ in range(3):
            agent.run_safe("Iran")
        ar = agent.run_safe("Iran")
        assert ar.is_fallback is True
        assert "circuit breaker open" in ar.error

    def test_half_open_attempt_after_reopen_cycles(self):
        agent = FailingAgent()
        agent._circuit_breaker = CircuitBreakerState(
            consecutive_failures=3,
            is_open=True,
            cycles_skipped=3,
            reopen_after_cycles=3,
        )
        ar = agent.run_safe("Iran")
        assert ar.is_fallback is True
        assert agent._circuit_breaker.is_open is True

    def test_success_resets_circuit_breaker(self):
        agent = SuccessAgent()
        agent._circuit_breaker = CircuitBreakerState(
            consecutive_failures=2,
            is_open=False,
        )
        agent.run_safe("Iran")
        assert agent._circuit_breaker.consecutive_failures == 0

    def test_half_open_success_closes_breaker(self):
        agent = SuccessAgent()
        agent._circuit_breaker = CircuitBreakerState(
            consecutive_failures=3,
            is_open=True,
            cycles_skipped=3,
            reopen_after_cycles=3,
        )
        agent.run_safe("Iran")
        assert agent._circuit_breaker.is_open is False
        assert agent._circuit_breaker.consecutive_failures == 0


class TestStateStoreIntegration:
    def test_stores_result(self):
        store = AgentStateStore()
        agent = SuccessAgent()
        agent.run_safe("Iran", store=store)
        entry = store.get_result("Iran", "test_success")
        assert entry is not None
        result, ts = entry
        assert isinstance(result, AgentResult)

    def test_stores_content_hash(self):
        store = AgentStateStore()
        agent = SuccessAgent()
        agent.run_safe("Iran", store=store)
        h = store.get_content_hash("Iran", "test_success")
        assert h is not None
        assert len(h) == 16

    def test_has_changed_on_different_data(self):
        store = AgentStateStore()
        a1 = SuccessAgent(EnergyResult(conflict="Iran", energy_score=42.0))
        a1.name = "energy"
        a1.run_safe("Iran", store=store)

        new_hash = BaseAgent._compute_hash(EnergyResult(conflict="Iran", energy_score=99.0))
        assert store.has_changed("Iran", "energy", new_hash)


class TestRunSafeDict:
    def test_returns_dict(self):
        agent = SuccessAgent()
        d = agent.run_safe_dict("Iran")
        assert isinstance(d, dict)
        assert "energy_score" in d

    def test_dict_preserves_score(self):
        agent = SuccessAgent(EnergyResult(conflict="Iran", energy_score=42.5))
        d = agent.run_safe_dict("Iran")
        assert d["energy_score"] == 42.5


class TestSchemaVersion:
    def test_base_result_has_schema_version(self):
        r = BaseAgentResult(conflict="test")
        assert r.schema_version == 1

    def test_energy_result_inherits_schema_version(self):
        r = EnergyResult(conflict="test")
        assert r.schema_version == 1
