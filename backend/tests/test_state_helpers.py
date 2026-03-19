"""Tests for api.state_helpers."""

from collections import deque

from api.state_helpers import (
    build_agent_status_from_result,
    push_agent_status,
    push_escalation_timeline,
    push_run_history,
)


def test_build_agent_status_from_result_empty():
    # Empty result yields default "ok" for all known agents
    got = build_agent_status_from_result({})
    assert isinstance(got, dict)
    assert all(got[k]["status"] == "ok" for k in got)
    assert set(got.keys()) == {
        "finint",
        "sigint",
        "news",
        "geoint",
        "socmint",
        "techint",
        "cyber",
        "energy",
        "protest",
        "diplo",
        "proximity",
        "narrative",
        "chokepoint",
    }


def test_build_agent_status_from_result_not_dict():
    assert build_agent_status_from_result(None) == {}
    assert build_agent_status_from_result([]) == {}


def test_build_agent_status_from_result_ok_agent():
    result = {
        "finint": {"sigint_score": 10, "_meta": {"duration_ms": 100, "confidence": 0.9}},
    }
    status = build_agent_status_from_result(result)
    assert "finint" in status
    assert status["finint"]["status"] == "ok"
    assert status["finint"]["duration_ms"] == 100
    assert status["finint"]["confidence"] == 0.9


def test_build_agent_status_from_result_error_agent():
    result = {
        "news": {"timeout_or_error": True, "_meta": {"error_summary": "timeout"}},
    }
    status = build_agent_status_from_result(result)
    assert status["news"]["status"] == "error"
    assert status["news"]["error_summary"] == "timeout"


def test_push_agent_status_legacy():
    class AppState:
        agent_status_last = {}

    push_agent_status(AppState(), {"finint": {"_meta": {"duration_ms": 50}}})
    assert AppState.agent_status_last.get("finint", {}).get("status") == "ok"


def test_push_escalation_timeline_legacy():
    class AppState:
        escalation_timeline_history = {}

    push_escalation_timeline(AppState(), "Iran", 1000.0, {"escalation_score": 55.0})
    assert "Iran" in AppState.escalation_timeline_history
    assert AppState.escalation_timeline_history["Iran"][-1]["escalation_score"] == 55.0


def test_push_run_history_legacy():
    class AppState:
        analysis_run_history = deque(maxlen=50)

    push_run_history(AppState(), "Iran", 1000.0, {"escalation_score": 60, "finint": {}})
    assert len(AppState.analysis_run_history) == 1
    entry = AppState.analysis_run_history[0]
    assert entry["conflict"] == "Iran"
    assert entry["escalation_score"] == 60
