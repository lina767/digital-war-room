"""Agent contract tests with strict Pydantic validation."""

import pytest
from pydantic import ValidationError

from agents.contracts import FinintResult, MediaintResult, SatintelResult, get_agent_fallback


def test_get_agent_fallback_finint_shape_is_stable():
    """Fallback should always return a schema-shaped dict for known agents."""
    fallback = get_agent_fallback("finint")
    assert isinstance(fallback, dict)
    assert "escalation_score" in fallback
    assert "summary" in fallback


def test_finint_result_rejects_string_for_float_field():
    """Strict mode must reject coercion from str -> float for score fields."""
    with pytest.raises(ValidationError):
        FinintResult(conflict="Iran", escalation_score="42.1")  # type: ignore[arg-type]


def test_finint_result_accepts_typed_score():
    """Typed numeric values should still validate correctly."""
    result = FinintResult(conflict="Iran", escalation_score=42.1, summary="ok")
    assert result.escalation_score == 42.1


def test_satintel_result_accepts_typed_score():
    result = SatintelResult(conflict="Iran", satintel_score=51.0, summary="ok")
    assert result.satintel_score == 51.0


def test_get_agent_fallback_satintel_shape_is_stable():
    fallback = get_agent_fallback("satintel")
    assert isinstance(fallback, dict)
    assert "satintel_score" in fallback
    assert "imagery_signals" in fallback


def test_mediaint_result_accepts_typed_score():
    result = MediaintResult(conflict="Iran", mediaint_score=33.0, summary="ok")
    assert result.mediaint_score == 33.0


def test_get_agent_fallback_mediaint_shape_is_stable():
    fallback = get_agent_fallback("mediaint")
    assert isinstance(fallback, dict)
    assert "mediaint_score" in fallback
    assert "media_assets" in fallback
    assert "vision_analysis_count" in fallback
