"""
Contracts for Gemini research enrichment.

The contract is intentionally strict:
- every accepted enrichment MUST carry a valid source URL
- each enrichment must target one concrete field path
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

ResearchTriggerType = Literal[
    "missing_required_fields",
    "stale_data",
    "agent_conflict",
    "high_uncertainty",
]


class ResearchTriggerReason(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    trigger: ResearchTriggerType
    detail: str = ""
    field_paths: List[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "medium"


class ResearchTriggerDecision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    triggered: bool = False
    reasons: List[ResearchTriggerReason] = Field(default_factory=list)
    missing_required_fields_count: int = 0
    stale_agents: List[str] = Field(default_factory=list)
    uncertainty_agents: List[str] = Field(default_factory=list)
    score_spread: float = 0.0


class ResearchEnrichmentItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    field_path: str = Field(min_length=1)
    value: Any
    source_url: HttpUrl
    source_title: str = ""
    fetched_at: str = ""
    confidence: float = Field(50.0, ge=0.0, le=100.0)
    note: str = ""


class ResearchRunBudget(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    max_requests_per_run: int = Field(1, ge=1)
    max_input_tokens_per_run: int = Field(0, ge=0)
    max_output_tokens_per_run: int = Field(0, ge=0)
    max_cost_usd_per_run: float = Field(0.0, ge=0.0)


class ResearchUsage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    requests: int = Field(0, ge=0)
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    estimated_cost_usd: float = Field(0.0, ge=0.0)


class ResearchBudgetStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    allowed: bool = True
    blocked_reason: Optional[str] = None
    budget: ResearchRunBudget
    usage: ResearchUsage


class ResearchEnrichmentResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    contract_version: int = 1
    triggered: bool = False
    trigger_decision: ResearchTriggerDecision = Field(default_factory=ResearchTriggerDecision)
    budget_status: ResearchBudgetStatus
    publish_decision: Literal["auto_publish", "human_review"] = "human_review"
    analysis_en: str = ""
    air_activity_assessment_en: str = ""
    findings: List[str] = Field(default_factory=list)
    enrichments_applied: List[ResearchEnrichmentItem] = Field(default_factory=list)
    enrichments_rejected: List[Dict[str, Any]] = Field(default_factory=list)
    source_coverage_ratio: float = Field(0.0, ge=0.0, le=1.0)
