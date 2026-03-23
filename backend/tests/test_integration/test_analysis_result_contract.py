"""Integration-level contract tests for the top-level analysis result."""

import pytest
from pydantic import ValidationError

from models.analysis import AnalysisResult


def test_analysis_result_accepts_agent_payloads_as_extra_fields():
    """Top-level model should allow per-agent payloads as extra fields."""
    payload = {
        "conflict": "Iran",
        "escalation_score": 55.0,
        "summary": "Synthetic integration payload",
        "finint": {"escalation_score": 40.0, "summary": "ok"},
        "sigint": {"sigint_score": 65.0, "summary": "ok"},
    }

    result = AnalysisResult.model_validate(payload)
    dumped = result.model_dump()

    assert dumped["conflict"] == "Iran"
    assert dumped["finint"]["summary"] == "ok"
    assert dumped["sigint"]["sigint_score"] == 65.0


def test_analysis_result_rejects_string_escalation_score_in_strict_mode():
    """Strict mode should reject implicit type coercion."""
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({"conflict": "Iran", "escalation_score": "75.5"})  # type: ignore[arg-type]


def test_analysis_result_schema_version_and_dq_fields():
    """Governance fields validate and default for older caches."""
    r = AnalysisResult.model_validate(
        {
            "conflict": "Iran",
            "analysis_result_schema_version": 1,
            "data_quality_gate": {"gate_version": 1, "quality_warnings": ["x"]},
            "quality_warnings": ["x"],
            "dq_calibration_metrics": {"calibration_schema_version": 1},
        }
    )
    assert r.analysis_result_schema_version == 1
    assert r.data_quality_gate["quality_warnings"] == ["x"]
