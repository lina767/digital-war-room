"""
Analysis result model – typed response from analyze_conflict (DAG/CEO).

Used at API boundaries and for validation. Per-agent payloads and
divisions remain as dynamic dicts (extra="allow").

Schema versioning: ``analysis_result_schema_version`` bumps when top-level
required fields change; keep in sync with CEO output and contract tests.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class AnalysisResult(BaseModel):
    """Full analysis response returned by analyze_conflict / CEO synthesis."""

    model_config = ConfigDict(strict=True, extra="allow", validate_assignment=True)

    analysis_result_schema_version: int = 2
    conflict: str = ""
    escalation_score: float = 0.0
    threat_level: str = "MINIMAL"
    key_findings: List[str] = Field(default_factory=list)
    key_findings_context: List[str] = Field(default_factory=list)
    key_findings_confidence: List[str] = Field(default_factory=list)
    next_steps: List[Dict[str, Any]] = Field(default_factory=list)
    root_cause_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    corroborated_patterns: List[Dict[str, Any]] = Field(default_factory=list)
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    narrative_story: str = ""
    actors: List[Dict[str, Any]] = Field(default_factory=list)
    predictive: Dict[str, Any] = Field(default_factory=dict)
    compliance: Dict[str, Any] = Field(default_factory=dict)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    pattern_flags: List[Dict[str, Any]] = Field(default_factory=list)
    satintel: Dict[str, Any] = Field(default_factory=dict)
    # Data quality (CEO pipeline); optional for older cached payloads
    data_quality_gate: Dict[str, Any] = Field(default_factory=dict)
    quality_warnings: List[str] = Field(default_factory=list)
    dq_calibration_metrics: Dict[str, Any] = Field(default_factory=dict)
    research_enrichment: Dict[str, Any] = Field(default_factory=dict)
    review_decision: str = "auto_publish"
    assessment: Dict[str, Any] = Field(default_factory=dict)

    # Per-agent results and divisions are stored via extra (finint, sigint, ..., divisions)
