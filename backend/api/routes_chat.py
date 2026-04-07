"""
Chat MVP routes for dashboard Q&A and feedback logging.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from agents.config import DEFAULT_CONFLICT
from api.deps import StateServiceDep
from middleware.rate_limit import limiter
from middleware.tenant_context import get_request_ctx
from services.haiku_service import analyst_summary
from services.chat_feedback_store import get_chat_feedback_summary, persist_chat_feedback
from utils.sanitize import CONFLICT_MAX_LEN, sanitize_conflict

router = APIRouter()

FALLBACK_TEXT = "Keine belastbare Antwort"
CONFIDENCE_MIN = 0.45
MAX_SOURCES = 8
SOURCE_FREE_QUESTION_TYPES = {"changes_since_yesterday"}
QuestionType = Literal[
    "situation_overview",
    "risk_assessment",
    "changes_since_yesterday",
    "next_24h_outlook",
    "source_check",
]


class ChatAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conflict: Optional[str] = Field(default=None, max_length=CONFLICT_MAX_LEN)

    @field_validator("question", mode="before")
    @classmethod
    def _strip_question(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("question must be a string")
        return v.strip()

    @field_validator("conflict", mode="before")
    @classmethod
    def _strip_optional_conflict(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("conflict must be a string")
        s = v.strip()
        return s if s else None

    @field_validator("conflict")
    @classmethod
    def _validate_conflict(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return sanitize_conflict(v)


class ChatAskResponse(BaseModel):
    response_id: str
    question_type: QuestionType
    answer: str
    confidence_score: float
    sources: List[str]
    fallback_used: bool


class ChatFeedbackRequest(BaseModel):
    response_id: str = Field(..., min_length=1, max_length=64)
    conflict: Optional[str] = Field(default=None, max_length=CONFLICT_MAX_LEN)
    question: str = Field(..., min_length=1, max_length=4000)
    question_type: str = Field(..., min_length=1, max_length=64)
    answer: str = Field(..., min_length=1, max_length=12000)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    sources: List[str] = Field(default_factory=list, max_length=30)
    helpful: bool
    comment: Optional[str] = Field(default=None, max_length=500)

    @field_validator("conflict", mode="before")
    @classmethod
    def _strip_feedback_conflict(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("conflict must be a string")
        s = v.strip()
        return s if s else None

    @field_validator("conflict")
    @classmethod
    def _validate_feedback_conflict(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return sanitize_conflict(v)

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, v: object) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("sources must be a list")
        out: List[str] = []
        for item in v[:30]:
            s = str(item).strip()
            if s:
                out.append(s[:500])
        return out


def _detect_question_type(question: str) -> QuestionType:
    q = question.lower()
    if any(k in q for k in ("since yesterday", "since last", "changed", "change", "new today", "what changed")):
        return "changes_since_yesterday"
    if any(k in q for k in ("risk", "danger", "threat", "escalation", "severity", "safe")):
        return "risk_assessment"
    if any(k in q for k in ("next 24h", "next 24", "next day", "tomorrow", "outlook", "forecast")):
        return "next_24h_outlook"
    if any(k in q for k in ("source", "evidence", "proof", "link", "citation", "where from")):
        return "source_check"
    return "situation_overview"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        s = (item or "").strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _collect_sources(analysis: Dict[str, Any]) -> List[str]:
    gathered: List[str] = []
    for key, block in analysis.items():
        if not isinstance(block, dict):
            continue
        meta = block.get("_meta")
        if not isinstance(meta, dict):
            continue
        for src in meta.get("sources") or []:
            if not isinstance(src, dict):
                continue
            for url in src.get("reference_urls") or []:
                if isinstance(url, str):
                    gathered.append(url.strip())
    news = analysis.get("news") or {}
    if isinstance(news, dict):
        for article in news.get("articles") or []:
            if isinstance(article, dict) and isinstance(article.get("url"), str):
                gathered.append(article["url"].strip())
    return _dedupe([s for s in gathered if s])[:MAX_SOURCES]


def _build_context(analysis: Dict[str, Any], fallback_conflict: str) -> str:
    conflict = str(analysis.get("conflict") or fallback_conflict)
    escalation = analysis.get("escalation_score")
    threat = analysis.get("threat_level")
    summary = str(analysis.get("summary") or "")
    findings = [str(f) for f in (analysis.get("key_findings") or []) if isinstance(f, str)][:8]
    scenarios = analysis.get("scenarios") or []
    scenario_lines: List[str] = []
    if isinstance(scenarios, list):
        for row in scenarios[:4]:
            if isinstance(row, dict):
                desc = str(row.get("description") or "").strip()
                prob = row.get("probability")
                if desc:
                    scenario_lines.append(f"- {desc} (probability={prob})")

    compliance = analysis.get("compliance") or {}
    risk_level = ""
    risk_drivers: List[str] = []
    if isinstance(compliance, dict):
        risk_score = compliance.get("risk_score") or {}
        if isinstance(risk_score, dict):
            risk_level = str(risk_score.get("level") or "")
            for driver in (risk_score.get("drivers") or [])[:5]:
                if isinstance(driver, dict):
                    factor = str(driver.get("factor") or "").strip()
                    detail = str(driver.get("detail") or "").strip()
                    if factor or detail:
                        risk_drivers.append(f"- {factor}: {detail}".strip(": "))
        ofac = compliance.get("ofac_sdn") or {}
        if isinstance(ofac, dict):
            sample_names = []
            for row in (ofac.get("sample") or [])[:10]:
                if isinstance(row, dict):
                    name = str(row.get("name") or "").strip()
                    if name:
                        sample_names.append(name)
            if sample_names:
                risk_drivers.append(f"- OFAC sample entities: {', '.join(sample_names)}")

    lines = [
        f"Conflict: {conflict}",
        f"Escalation score: {escalation}",
        f"Threat level: {threat}",
        f"Summary: {summary}",
        "Key findings:",
        *[f"- {f}" for f in findings],
    ]
    if scenario_lines:
        lines.append("Scenarios:")
        lines.extend(scenario_lines)
    if risk_level:
        lines.append(f"Compliance risk level: {risk_level}")
    if risk_drivers:
        lines.append("Compliance/document context:")
        lines.extend(risk_drivers)
    return "\n".join(lines)[:12000]


def _safe_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _build_fallback(question_type: QuestionType, response_id: str) -> ChatAskResponse:
    return ChatAskResponse(
        response_id=response_id,
        question_type=question_type,
        answer=FALLBACK_TEXT,
        confidence_score=0.0,
        sources=[],
        fallback_used=True,
    )


@router.post("/chat/ask")
@limiter.limit("20/minute")
async def chat_ask(request: Request, state: StateServiceDep, body: ChatAskRequest) -> ChatAskResponse:
    question = body.question.strip()
    conflict = body.conflict or DEFAULT_CONFLICT
    response_id = str(uuid.uuid4())
    question_type = _detect_question_type(question)
    cached = state.get_cache(conflict, tenant_id=get_request_ctx(request).tenant_id)
    if not cached or not isinstance(cached.get("result"), dict):
        return _build_fallback(question_type, response_id)
    analysis = cached["result"]
    context = _build_context(analysis, conflict)
    sources = _collect_sources(analysis)

    system = (
        "You are a geopolitical analyst assistant for a dashboard chat MVP.\n"
        "Answer strictly in English, based only on provided context.\n"
        "Never fabricate facts or sources.\n"
        "Return only valid JSON with keys: answer, confidence_score, sources.\n"
        "confidence_score must be a float between 0 and 1.\n"
        "sources must be an array with source strings."
    )
    user_content = (
        f"Question type: {question_type}\n"
        f"Question: {question}\n\n"
        f"Context:\n{context}\n\n"
        f"Candidate sources:\n{json.dumps(sources)}\n"
    )
    raw = await analyst_summary(system=system, data=user_content, max_tokens=450, usage_agent="analyst")
    if not raw:
        return _build_fallback(question_type, response_id)
    parsed = _safe_parse_json(raw)
    if not parsed:
        return _build_fallback(question_type, response_id)

    answer = str(parsed.get("answer") or "").strip()
    try:
        confidence = float(parsed.get("confidence_score") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    out_sources_raw = parsed.get("sources")
    out_sources = _dedupe([str(s).strip() for s in out_sources_raw if isinstance(s, str)])[:MAX_SOURCES] if isinstance(out_sources_raw, list) else []
    if not out_sources:
        out_sources = sources[:MAX_SOURCES]

    if (
        not answer
        or confidence < CONFIDENCE_MIN
        or (question_type not in SOURCE_FREE_QUESTION_TYPES and len(out_sources) == 0)
    ):
        return _build_fallback(question_type, response_id)

    return ChatAskResponse(
        response_id=response_id,
        question_type=question_type,
        answer=answer,
        confidence_score=confidence,
        sources=out_sources,
        fallback_used=False,
    )


@router.post("/chat/feedback")
@limiter.limit("60/minute")
async def chat_feedback(request: Request, body: ChatFeedbackRequest) -> Dict[str, Any]:
    tenant_id = str(get_request_ctx(request).tenant_id)
    feedback_row = {
        "tenant_id": tenant_id,
        "response_id": body.response_id,
        "conflict": body.conflict or DEFAULT_CONFLICT,
        "question_type": body.question_type,
        "question": body.question,
        "answer": body.answer,
        "confidence_score": body.confidence_score,
        "sources": body.sources,
        "helpful": body.helpful,
        "comment": body.comment,
    }
    persisted = await persist_chat_feedback(feedback_row)
    return {"status": "ok", **persisted}


@router.get("/chat/feedback/summary")
@limiter.limit("20/minute")
async def chat_feedback_summary(request: Request, days: int = 7, limit: int = 500) -> Dict[str, Any]:
    tenant_id = str(get_request_ctx(request).tenant_id)
    summary = await get_chat_feedback_summary(tenant_id=tenant_id, days=days, limit=limit)
    return {"status": "ok", "days": max(1, min(int(days), 90)), **summary}
