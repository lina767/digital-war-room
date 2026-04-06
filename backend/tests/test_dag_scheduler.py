"""
Tests for DAGScheduler: topological ordering, parallel execution,
optional_deps, timeout_s, streamable, ResultStore, ResultStoreManager.
"""

import time

import pytest

from agents.dag_scheduler import (
    DAGNode,
    DAGScheduler,
    ResultStore,
    ResultStoreManager,
)

# ---------------------------------------------------------------------------
# ResultStore tests
# ---------------------------------------------------------------------------


class TestResultStore:
    def test_set_and_get(self):
        store = ResultStore(cycle_id="c1", conflict="Iran")
        store.set("sigint", {"score": 65})
        assert store.get("sigint") == {"score": 65}

    def test_get_returns_none_for_missing(self):
        store = ResultStore()
        assert store.get("nonexistent") is None

    def test_has(self):
        store = ResultStore()
        store.set("a", 1)
        assert store.has("a")
        assert not store.has("b")

    def test_contains(self):
        store = ResultStore()
        store.set("x", 42)
        assert "x" in store
        assert "y" not in store

    def test_get_many(self):
        store = ResultStore()
        store.set("a", 1)
        store.set("b", 2)
        result = store.get_many(["a", "b", "c"])
        assert result == {"a": 1, "b": 2, "c": None}

    def test_all_results(self):
        store = ResultStore()
        store.set("a", 1)
        store.set("b", 2)
        assert store.all_results() == {"a": 1, "b": 2}

    def test_lifecycle_fields(self):
        store = ResultStore(cycle_id="c123", conflict="Taiwan")
        assert store.cycle_id == "c123"
        assert store.conflict == "Taiwan"
        assert store.created_at > 0


# ---------------------------------------------------------------------------
# ResultStoreManager tests
# ---------------------------------------------------------------------------


class TestResultStoreManager:
    def test_create_store(self):
        mgr = ResultStoreManager()
        store = mgr.create_store("Iran", "cycle-001")
        assert store.conflict == "Iran"
        assert store.cycle_id == "cycle-001"

    def test_cleanup_retains_latest(self):
        mgr = ResultStoreManager(retention_cycles=2, retention_minutes=999)
        for i in range(5):
            mgr.create_store("Iran", f"c{i}")
        mgr.cleanup()
        assert len(mgr._stores) == 2

    def test_cleanup_removes_old_by_time(self):
        mgr = ResultStoreManager(retention_cycles=999, retention_minutes=0)
        store = mgr.create_store("Iran", "old")
        store.created_at = time.time() - 3600
        mgr.cleanup()
        assert len(mgr._stores) == 0


# ---------------------------------------------------------------------------
# DAGScheduler – basic execution
# ---------------------------------------------------------------------------


class TestDAGSchedulerBasic:
    def test_single_node(self):
        nodes = [DAGNode(id="a", node_type="agent")]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {"a": lambda s: 42}
        scheduler.run(executors, store)
        assert store.get("a") == 42

    def test_linear_chain(self):
        nodes = [
            DAGNode(id="a", node_type="agent"),
            DAGNode(id="b", dependencies=["a"], node_type="enrichment"),
            DAGNode(id="c", dependencies=["b"], node_type="synthesis"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()

        def exec_a(s):
            return 10

        def exec_b(s):
            return s.get("a") * 2

        def exec_c(s):
            return s.get("b") + 1

        executors = {"a": exec_a, "b": exec_b, "c": exec_c}
        scheduler.run(executors, store)
        assert store.get("a") == 10
        assert store.get("b") == 20
        assert store.get("c") == 21

    def test_parallel_independent(self):
        nodes = [
            DAGNode(id="a", node_type="agent"),
            DAGNode(id="b", node_type="agent"),
            DAGNode(id="c", node_type="agent"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "a": lambda s: "A",
            "b": lambda s: "B",
            "c": lambda s: "C",
        }
        scheduler.run(executors, store)
        assert store.get("a") == "A"
        assert store.get("b") == "B"
        assert store.get("c") == "C"

    def test_diamond_deps(self):
        nodes = [
            DAGNode(id="a", node_type="agent"),
            DAGNode(id="b", dependencies=["a"], node_type="enrichment"),
            DAGNode(id="c", dependencies=["a"], node_type="enrichment"),
            DAGNode(id="d", dependencies=["b", "c"], node_type="synthesis"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "a": lambda s: 1,
            "b": lambda s: s.get("a") + 10,
            "c": lambda s: s.get("a") + 20,
            "d": lambda s: s.get("b") + s.get("c"),
        }
        scheduler.run(executors, store)
        assert store.get("d") == 32


# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------


class TestOptionalDeps:
    def test_runs_when_optional_dep_missing(self):
        nodes = [
            DAGNode(id="a", node_type="agent"),
            DAGNode(id="b", optional_deps=["missing_node"], node_type="enrichment"),
        ]
        nodes.append(DAGNode(id="missing_node", node_type="agent"))
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "a": lambda s: "A",
            "b": lambda s: f"B+{s.get('missing_node')}",
        }
        scheduler.run(executors, store)
        assert store.get("b") == "B+None"

    def test_uses_optional_dep_when_available(self):
        nodes = [
            DAGNode(id="ner", node_type="enrichment"),
            DAGNode(id="finint_enrich", optional_deps=["ner"], node_type="enrichment"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "ner": lambda s: ["entity1", "entity2"],
            "finint_enrich": lambda s: f"enriched with {s.get('ner')}",
        }
        scheduler.run(executors, store)
        assert "entity1" in store.get("finint_enrich")


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestDAGTimeout:
    def test_node_timeout_uses_fallback(self):
        nodes = [
            DAGNode(id="slow", node_type="agent", timeout_s=0.3, fallback={"score": 0}),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()

        def slow_exec(s):
            time.sleep(5)
            return {"score": 99}

        executors = {"slow": slow_exec}
        scheduler.run(executors, store)
        assert store.get("slow") == {"score": 0}


# ---------------------------------------------------------------------------
# Streamable
# ---------------------------------------------------------------------------


class TestStreamable:
    def test_only_streamable_nodes_yielded(self):
        nodes = [
            DAGNode(id="agent_a", node_type="agent", streamable=True),
            DAGNode(id="enrich", dependencies=["agent_a"], node_type="enrichment", streamable=False),
            DAGNode(id="summary", dependencies=["enrich"], node_type="division_summary", streamable=True),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "agent_a": lambda s: "A",
            "enrich": lambda s: "E",
            "summary": lambda s: "S",
        }
        events = list(scheduler.run_streaming(executors, store))
        event_ids = [e[0] for e in events]
        assert "agent_a" in event_ids
        assert "summary" in event_ids
        assert "enrich" not in event_ids

    def test_streaming_results_in_store(self):
        nodes = [
            DAGNode(id="a", node_type="agent", streamable=True),
            DAGNode(id="b", dependencies=["a"], node_type="enrichment"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "a": lambda s: "data_a",
            "b": lambda s: "data_b",
        }
        list(scheduler.run_streaming(executors, store))
        assert store.get("a") == "data_a"
        assert store.get("b") == "data_b"

    def test_streaming_timeout_yields_fallback_payload(self):
        nodes = [
            DAGNode(id="slow", node_type="agent", streamable=True, timeout_s=0.2, fallback={"score": 0, "fallback": True}),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()

        def slow_exec(s):
            time.sleep(3)
            return {"score": 99}

        events = list(scheduler.run_streaming({"slow": slow_exec}, store))
        assert events == [("slow", {"score": 0, "fallback": True})]
        assert store.get("slow") == {"score": 0, "fallback": True}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestDAGErrorHandling:
    def test_node_failure_uses_fallback(self):
        nodes = [
            DAGNode(id="bad", node_type="agent", fallback={"error": True}),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()

        def bad_exec(s):
            raise RuntimeError("boom")

        executors = {"bad": bad_exec}
        scheduler.run(executors, store)
        assert store.get("bad") == {"error": True}

    def test_missing_executor_uses_fallback(self):
        nodes = [
            DAGNode(id="no_exec", node_type="agent", fallback="default"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        scheduler.run({}, store)
        assert store.get("no_exec") == "default"

    def test_downstream_runs_with_fallback_data(self):
        nodes = [
            DAGNode(id="a", node_type="agent", fallback=0),
            DAGNode(id="b", dependencies=["a"], node_type="enrichment"),
        ]
        scheduler = DAGScheduler(nodes)
        store = ResultStore()
        executors = {
            "a": lambda s: (_ for _ in ()).throw(RuntimeError("fail")),
            "b": lambda s: (s.get("a") or 0) + 100,
        }
        scheduler.run(executors, store)
        assert store.get("b") == 100


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestDAGValidation:
    def test_unknown_hard_dep_raises(self):
        nodes = [DAGNode(id="a", dependencies=["nonexistent"], node_type="agent")]
        with pytest.raises(ValueError, match="unknown hard dep"):
            DAGScheduler(nodes)

    def test_unknown_optional_dep_raises(self):
        nodes = [DAGNode(id="a", optional_deps=["nonexistent"], node_type="agent")]
        with pytest.raises(ValueError, match="unknown optional dep"):
            DAGScheduler(nodes)
