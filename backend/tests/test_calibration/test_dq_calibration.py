"""Calibration metrics from analysis dicts."""

from calibration.dq_calibration import compute_calibration_metrics


def test_compute_calibration_metrics_minimal():
    r = {
        "degraded_agents": ["finint"],
        "finint": {"dq_confidence": 20.0, "_meta": {"fallback_used": True}},
        "news": {"dq_confidence": 80.0, "_meta": {"fallback_used": False}},
        "data_quality_gate": {"quality_warnings": ["a"], "gate_confidence": 55.0},
    }
    m = compute_calibration_metrics(r)
    assert m["calibration_schema_version"] == 1
    assert m["degraded_agent_count"] == 1
    assert m["quality_warning_count"] == 1
    assert m["mean_dq_confidence"] is not None
