"""
Chat MVP routes for dashboard Q&A and feedback logging.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Literal, Optional, Set

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from agents.config import DEFAULT_CONFLICT
from api.deps import StateServiceDep
from middleware.rate_limit import limiter
from middleware.tenant_context import get_request_ctx
from services.haiku_service import analyst_summary
from services.chat_feedback_store import (
    get_chat_feedback_summary,
    persist_chat_feedback,
    persist_chat_response,
    resolve_chat_response,
)
from utils.sanitize import CONFLICT_MAX_LEN, sanitize_conflict

router = APIRouter()

FALLBACK_TEXT = "Keine belastbare Antwort"
CONFIDENCE_MIN = float(os.getenv("CHAT_CONFIDENCE_MIN", "0.30"))
SOURCE_REQUIRED_CONFIDENCE = float(os.getenv("CHAT_SOURCE_REQUIRED_CONFIDENCE", "0.60"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "800"))
MAX_SOURCES = 8
SOURCE_FREE_QUESTION_TYPES = {"changes_since_yesterday"}
CONTEXT_CHAR_BUDGET = 12000
PRIMARY_CONTEXT_BUDGET = 8000
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
    helpful: bool
    comment: Optional[str] = Field(default=None, max_length=500)


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
    return _build_context_for_type(analysis, fallback_conflict, "situation_overview")


def _short_text(value: Any, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _slice_items(value: Any, limit: int = 3) -> List[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _dict_items_as_text(rows: List[Any], keys: List[str], item_limit: int = 3) -> List[str]:
    out: List[str] = []
    for row in rows[:item_limit]:
        if isinstance(row, dict):
            parts = []
            for k in keys:
                v = row.get(k)
                if v is None:
                    continue
                s = _short_text(v, 140)
                if s:
                    parts.append(f"{k}={s}")
            if parts:
                out.append("- " + "; ".join(parts))
        elif isinstance(row, str):
            s = _short_text(row, 180)
            if s:
                out.append(f"- {s}")
    return out


def _extract_agent_context(agent_key: str, block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    lines: List[str] = []
    summary = _short_text(block.get("summary"), 320)
    if summary:
        lines.append(f"{agent_key.upper()} summary: {summary}")

    if agent_key == "chokepoint":
        lines.extend(_dict_items_as_text(_slice_items(block.get("chokepoints"), 3), ["name", "status", "risk"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("gdelt_disruption"), 3), ["title", "source", "url"], 3))
    elif agent_key == "sigint":
        lines.extend(_dict_items_as_text(_slice_items(block.get("aircraft"), 4), ["callsign", "category", "operator"], 4))
        lines.extend(_dict_items_as_text(_slice_items(block.get("ships"), 3), ["name", "flag", "location"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("conflict_reports"), 3), ["title", "source", "url"], 3))
    elif agent_key == "cyber":
        lines.extend(_dict_items_as_text(_slice_items(block.get("greynoise_scan_context"), 3), ["ip", "classification", "last_seen"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("cisa_kev"), 3), ["cve", "vendor_project", "product"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("threat_reports"), 3), ["title", "source", "url"], 3))
    elif agent_key == "energy":
        lines.extend(_dict_items_as_text(_slice_items(block.get("commodities"), 3), ["name", "price", "change_pct"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("food_security_risk"), 3), ["country", "risk_level", "driver"], 3))
    elif agent_key == "finint":
        lines.extend(_dict_items_as_text(_slice_items(block.get("polymarket"), 3), ["question", "probability", "volume"], 3))
        if isinstance(block.get("brent"), dict):
            lines.append(f"- brent={_short_text(json.dumps(block.get('brent')), 180)}")
        if isinstance(block.get("wti"), dict):
            lines.append(f"- wti={_short_text(json.dumps(block.get('wti')), 180)}")
        if block.get("fear_greed") is not None:
            lines.append(f"- fear_greed={_short_text(block.get('fear_greed'), 120)}")
    elif agent_key == "news":
        lines.extend(_dict_items_as_text(_slice_items(block.get("articles"), 5), ["title", "source", "sentiment", "url"], 5))
    elif agent_key == "socmint":
        lines.extend(_dict_items_as_text(_slice_items(block.get("top_signals"), 4), ["platform", "signal", "score"], 4))
        if block.get("total_signals") is not None:
            lines.append(f"- total_signals={_short_text(block.get('total_signals'), 80)}")
    elif agent_key == "geoint":
        lines.extend(_dict_items_as_text(_slice_items(block.get("anomalies"), 3), ["label", "severity", "location"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("hotspots"), 3), ["name", "confidence", "location"], 3))
    elif agent_key == "diplo":
        lines.extend(_dict_items_as_text(_slice_items(block.get("ofac_sdn"), 3), ["name", "program", "reference"], 3))
        lines.extend(_dict_items_as_text(_slice_items(block.get("eu_sanctions"), 3), ["name", "category", "reference"], 3))
    elif agent_key == "proximity":
        lines.extend(_dict_items_as_text(_slice_items(block.get("evidence"), 4), ["label", "detail", "score"], 4))
    elif agent_key == "narrative":
        if block.get("synthesis_text"):
            lines.append(f"- synthesis_text={_short_text(block.get('synthesis_text'), 320)}")
        if block.get("synthesis_probability") is not None:
            lines.append(f"- synthesis_probability={_short_text(block.get('synthesis_probability'), 80)}")
    elif agent_key == "pentagon":
        lines.extend(_dict_items_as_text(_slice_items(block.get("venues"), 3), ["name", "status", "location"], 3))

    return "\n".join(lines).strip()


def _extract_compliance_context(analysis: Dict[str, Any]) -> str:
    compliance = analysis.get("compliance")
    if not isinstance(compliance, dict):
        return ""
    lines: List[str] = []
    risk_score = compliance.get("risk_score")
    if isinstance(risk_score, dict):
        level = _short_text(risk_score.get("level"), 120)
        if level:
            lines.append(f"COMPLIANCE risk level: {level}")
        for driver in _slice_items(risk_score.get("drivers"), 5):
            if isinstance(driver, dict):
                factor = _short_text(driver.get("factor"), 120)
                detail = _short_text(driver.get("detail"), 180)
                if factor or detail:
                    lines.append(f"- {factor}: {detail}".strip(": "))
    ofac = compliance.get("ofac_sdn")
    if isinstance(ofac, dict):
        sample_names = []
        for row in _slice_items(ofac.get("sample"), 10):
            if isinstance(row, dict):
                name = _short_text(row.get("name"), 80)
                if name:
                    sample_names.append(name)
        if sample_names:
            lines.append(f"- OFAC sample entities: {', '.join(sample_names)}")
    return "\n".join(lines).strip()


def _extract_scenarios_context(analysis: Dict[str, Any]) -> str:
    scenarios = analysis.get("scenarios")
    if not isinstance(scenarios, list):
        return ""
    lines = ["SCENARIOS:"]
    for row in scenarios[:4]:
        if isinstance(row, dict):
            desc = _short_text(row.get("description"), 220)
            prob = row.get("probability")
            if desc:
                lines.append(f"- {desc} (probability={prob})")
    return "\n".join(lines)


def _has_reference_urls(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    meta = block.get("_meta")
    if not isinstance(meta, dict):
        return False
    for src in meta.get("sources") or []:
        if not isinstance(src, dict):
            continue
        if any(isinstance(u, str) and u.strip() for u in (src.get("reference_urls") or [])):
            return True
    return False


def _question_context_plan(question_type: QuestionType, analysis: Dict[str, Any]) -> Dict[str, List[str]]:
    if question_type == "risk_assessment":
        return {
            "primary": ["compliance", "finint", "proximity"],
            "secondary": ["cyber", "energy", "news"],
        }
    if question_type == "changes_since_yesterday":
        secondary_agents = [k for k in analysis.keys() if isinstance(analysis.get(k), dict) and analysis.get(k, {}).get("summary")]
        return {
            "primary": ["news", "socmint", "narrative"],
            "secondary": secondary_agents,
        }
    if question_type == "next_24h_outlook":
        return {
            "primary": ["scenarios", "narrative", "cyber", "energy"],
            "secondary": ["finint", "sigint", "chokepoint"],
        }
    if question_type == "source_check":
        primary = [k for k, v in analysis.items() if isinstance(v, dict) and _has_reference_urls(v)]
        return {
            "primary": primary,
            "secondary": ["news"],
        }
    return {
        "primary": ["news", "narrative", "socmint"],
        "secondary": ["sigint", "geoint", "diplo"],
    }


def _build_context_for_type(analysis: Dict[str, Any], fallback_conflict: str, question_type: QuestionType) -> str:
    conflict = str(analysis.get("conflict") or fallback_conflict)
    escalation = analysis.get("escalation_score")
    threat = analysis.get("threat_level")
    summary = _short_text(analysis.get("summary"), 600)
    findings = [str(f) for f in (analysis.get("key_findings") or []) if isinstance(f, str)][:8]

    header_lines = [
        f"Conflict: {conflict}",
        f"Escalation score: {escalation}",
        f"Threat level: {threat}",
        f"Question type: {question_type}",
        f"Summary: {summary}",
        "Key findings:",
        *[f"- {_short_text(f, 220)}" for f in findings],
    ]
    header = "\n".join(header_lines).strip()

    plan = _question_context_plan(question_type, analysis)
    chunks: List[str] = [header]
    used = len(header)
    seen_keys: Set[str] = set()

    def add_chunk(text: str, budget: int) -> bool:
        nonlocal used
        chunk = (text or "").strip()
        if not chunk:
            return False
        if used + len(chunk) + 2 > budget:
            return False
        chunks.append(chunk)
        used += len(chunk) + 2
        return True

    for key in plan.get("primary", []):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key == "compliance":
            add_chunk(_extract_compliance_context(analysis), PRIMARY_CONTEXT_BUDGET)
            continue
        if key == "scenarios":
            add_chunk(_extract_scenarios_context(analysis), PRIMARY_CONTEXT_BUDGET)
            continue
        add_chunk(_extract_agent_context(key, analysis.get(key)), PRIMARY_CONTEXT_BUDGET)

    for key in plan.get("secondary", []):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key == "compliance":
            add_chunk(_extract_compliance_context(analysis), CONTEXT_CHAR_BUDGET)
            continue
        if key == "scenarios":
            add_chunk(_extract_scenarios_context(analysis), CONTEXT_CHAR_BUDGET)
            continue
        add_chunk(_extract_agent_context(key, analysis.get(key)), CONTEXT_CHAR_BUDGET)

    return "\n\n".join(chunks)[:CONTEXT_CHAR_BUDGET]


def _fallback_agent_sources(question_type: QuestionType, analysis: Dict[str, Any]) -> List[str]:
    labels = {
        "situation_overview": ["NEWS analysis", "NARRATIVE synthesis", "SOCMINT monitoring"],
        "risk_assessment": ["COMPLIANCE risk model", "FININT indicators", "PROXIMITY evidence"],
        "changes_since_yesterday": ["NEWS updates", "SOCMINT updates", "NARRATIVE synthesis"],
        "next_24h_outlook": ["SCENARIO projection", "CYBER indicators", "ENERGY indicators"],
        "source_check": ["Cross-agent provenance index"],
    }
    planned = labels.get(question_type, [])
    out: List[str] = []
    for label in planned:
        if "COMPLIANCE" in label and isinstance(analysis.get("compliance"), dict):
            out.append(label)
            continue
        if "SCENARIO" in label and isinstance(analysis.get("scenarios"), list):
            out.append(label)
            continue
        agent_key = label.split(" ")[0].lower()
        if isinstance(analysis.get(agent_key), dict):
            out.append(label)
    return _dedupe(out)[:MAX_SOURCES]


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
    tenant_id = str(get_request_ctx(request).tenant_id)
    cached = state.get_cache(conflict, tenant_id=tenant_id)
    if not cached or not isinstance(cached.get("result"), dict):
        response = _build_fallback(question_type, response_id)
        await persist_chat_response(
            {
                "tenant_id": tenant_id,
                "response_id": response.response_id,
                "conflict": conflict,
                "question_type": response.question_type,
                "question": question,
                "answer": response.answer,
                "confidence_score": response.confidence_score,
                "sources": response.sources,
                "fallback_used": response.fallback_used,
            }
        )
        return response
    analysis = cached["result"]
    context = _build_context_for_type(analysis, conflict, question_type)
    sources = _collect_sources(analysis)

    system = (
        "You are a geopolitical analyst assistant for a dashboard chat MVP.\n"
        "Answer strictly in English, based only on provided context.\n"
        "Never fabricate facts or sources.\n"
        "Prefer a partial answer with caveats over refusing to answer.\n"
        "Confidence calibration:\n"
        "- >=0.70: grounded in multiple context signals.\n"
        "- 0.50-0.69: grounded but limited to partial or single-source context.\n"
        "- 0.30-0.49: plausible inference from context with uncertainty.\n"
        "- <0.30: context insufficient for a meaningful answer.\n"
        "Answer format: 1-3 sentence lead, then concise bullet points when useful.\n"
        "Return only valid JSON with keys: answer, confidence_score, sources.\n"
        "confidence_score must be a float between 0 and 1.\n"
        "sources must be an array with source strings.\n"
        'Example: {"answer":"Risk remains elevated due to maritime and sanctions pressure.","confidence_score":0.64,"sources":["https://example.com/report"]}'
    )
    user_content = (
        f"Question type: {question_type}\n"
        f"Question: {question}\n\n"
        f"Context:\n{context}\n\n"
        f"Candidate sources:\n{json.dumps(sources)}\n"
    )
    raw = await analyst_summary(system=system, data=user_content, max_tokens=CHAT_MAX_TOKENS, usage_agent="analyst")
    if not raw:
        response = _build_fallback(question_type, response_id)
        await persist_chat_response(
            {
                "tenant_id": tenant_id,
                "response_id": response.response_id,
                "conflict": conflict,
                "question_type": response.question_type,
                "question": question,
                "answer": response.answer,
                "confidence_score": response.confidence_score,
                "sources": response.sources,
                "fallback_used": response.fallback_used,
            }
        )
        return response
    parsed = _safe_parse_json(raw)
    if not parsed:
        response = _build_fallback(question_type, response_id)
        await persist_chat_response(
            {
                "tenant_id": tenant_id,
                "response_id": response.response_id,
                "conflict": conflict,
                "question_type": response.question_type,
                "question": question,
                "answer": response.answer,
                "confidence_score": response.confidence_score,
                "sources": response.sources,
                "fallback_used": response.fallback_used,
            }
        )
        return response

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
    if not out_sources:
        out_sources = _fallback_agent_sources(question_type, analysis)

    requires_sources = question_type == "source_check" or confidence >= SOURCE_REQUIRED_CONFIDENCE
    if (
        not answer
        or confidence < CONFIDENCE_MIN
        or (requires_sources and question_type not in SOURCE_FREE_QUESTION_TYPES and len(out_sources) == 0)
    ):
        response = _build_fallback(question_type, response_id)
        await persist_chat_response(
            {
                "tenant_id": tenant_id,
                "response_id": response.response_id,
                "conflict": conflict,
                "question_type": response.question_type,
                "question": question,
                "answer": response.answer,
                "confidence_score": response.confidence_score,
                "sources": response.sources,
                "fallback_used": response.fallback_used,
            }
        )
        return response

    response = ChatAskResponse(
        response_id=response_id,
        question_type=question_type,
        answer=answer,
        confidence_score=confidence,
        sources=out_sources,
        fallback_used=False,
    )
    await persist_chat_response(
        {
            "tenant_id": tenant_id,
            "response_id": response.response_id,
            "conflict": conflict,
            "question_type": response.question_type,
            "question": question,
            "answer": response.answer,
            "confidence_score": response.confidence_score,
            "sources": response.sources,
            "fallback_used": response.fallback_used,
        }
    )
    return response


@router.post("/chat/feedback")
@limiter.limit("60/minute")
async def chat_feedback(request: Request, body: ChatFeedbackRequest) -> Dict[str, Any]:
    tenant_id = str(get_request_ctx(request).tenant_id)
    resolved = await resolve_chat_response(response_id=body.response_id, tenant_id=tenant_id)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "response_id": body.response_id},
        )
    feedback_row = {
        "tenant_id": tenant_id,
        "response_id": body.response_id,
        "conflict": resolved.get("conflict") or DEFAULT_CONFLICT,
        "question_type": resolved.get("question_type") or "situation_overview",
        "question": resolved.get("question") or "",
        "answer": resolved.get("answer") or "",
        "confidence_score": float(resolved.get("confidence_score") or 0.0),
        "sources": list(resolved.get("sources") or []),
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
