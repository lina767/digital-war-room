"""Tests for thread-local analysis run state (peer reads without supervisor)."""

from agents.analysis_run_state import (
    get_current_conflict,
    get_current_cycle_id,
    get_peer_result,
    get_peer_results,
    get_peers_snapshot,
    invoke_with_current_store,
)
from agents.dag_scheduler import DAGNode, DAGScheduler, ResultStore


def test_outside_run_no_peer():
    assert get_peer_result("sigint") is None
    assert get_peer_results(["sigint", "news"]) == {"sigint": None, "news": None}
    assert get_peers_snapshot() == {}
    assert get_current_conflict() == ""
    assert get_current_cycle_id() == ""


def test_invoke_exposes_peer_reads():
    store = ResultStore(cycle_id="c-test", conflict="Iran")
    store.set("sigint", {"sigint_score": 42, "summary": "x"})
    store.set("news", {"news_score": 10})

    def inner(_s):
        assert get_current_conflict() == "Iran"
        assert get_current_cycle_id() == "c-test"
        assert get_peer_result("sigint") == {"sigint_score": 42, "summary": "x"}
        assert get_peer_results(["sigint", "missing"])["missing"] is None
        assert get_peers_snapshot(exclude="news") == {"sigint": {"sigint_score": 42, "summary": "x"}}
        return "ok"

    assert invoke_with_current_store(store, inner) == "ok"
    assert get_peer_result("sigint") is None


def test_nested_invoke_restores_previous():
    outer = ResultStore(cycle_id="o", conflict="A")
    inner_store = ResultStore(cycle_id="i", conflict="B")
    outer.set("k", "outer-val")
    inner_store.set("k", "inner-val")

    seen = []

    def inner(_s):
        seen.append(get_peer_result("k"))
        return None

    def outer_fn(_s):
        seen.append(get_peer_result("k"))
        invoke_with_current_store(inner_store, inner)
        seen.append(get_peer_result("k"))
        return None

    invoke_with_current_store(outer, outer_fn)
    assert seen == ["outer-val", "inner-val", "outer-val"]


def test_dag_scheduler_binds_store_per_node():
    store = ResultStore(cycle_id="dag", conflict="Taiwan")
    nodes = [
        DAGNode(id="a", dependencies=[], timeout_s=5.0),
        DAGNode(id="b", dependencies=["a"], timeout_s=5.0),
    ]

    def exec_a(_s):
        return {"a": 1, "done": True}

    def exec_b(_s):
        return {"from_peer": get_peer_result("a")}

    sched = DAGScheduler(nodes, max_workers=2)
    sched.run({"a": exec_a, "b": exec_b}, store)
    assert store.get("b") == {"from_peer": {"a": 1, "done": True}}
