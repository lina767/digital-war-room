"""
Chat MVP routes for dashboard Q&A and feedback logging.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
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

import asyncio
import logging
import re

import httpx

_chat_logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_TEXT = "No reliable answer available."
CONFIDENCE_MIN = float(os.getenv("CHAT_CONFIDENCE_MIN", "0.30"))
LOW_CONFIDENCE_FLOOR = float(os.getenv("CHAT_LOW_CONFIDENCE_MIN", "0.05"))
SOURCE_REQUIRED_CONFIDENCE = float(os.getenv("CHAT_SOURCE_REQUIRED_CONFIDENCE", "0.60"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "800"))
MAX_SOURCES = 8
SOURCE_FREE_QUESTION_TYPES = {"changes_since_yesterday"}
CONTEXT_CHAR_BUDGET = 12000
# Per agent / section chunk after header (plan: ~700–900; avoids one stream consuming the whole budget).
AGENT_CHUNK_MAX_CHARS = int(os.getenv("CHAT_AGENT_CHUNK_MAX_CHARS", "800"))
# Recency window for changes_since_yesterday (NEWS published_at, SIGINT _meta.fetched_at).
CHANGES_RECENT_HOURS = int(os.getenv("CHAT_CHANGES_RECENT_HOURS", "36"))
# Max chars for Layer 4 deterministic diff block inside chat context (rest stays for snapshot excerpts).
CHAT_DIFF_CONTEXT_MAX_CHARS = int(os.getenv("CHAT_DIFF_CONTEXT_MAX_CHARS", "4500"))

QuestionType = Literal[
    "situation_overview",
    "risk_assessment",
    "changes_since_yesterday",
    "next_24h_outlook",
    "source_check",
]

QUESTION_TYPE_AGENTS: Dict[QuestionType, Dict[str, List[str]]] = {
    "situation_overview": {
        "primary": ["news", "geoint", "diplo"],
        "secondary": ["sigint", "narrative"],
    },
    "risk_assessment": {
        "primary": ["compliance", "finint", "cyber", "chokepoint", "socmint"],
        "secondary": ["narrative", "proximity"],
    },
    "changes_since_yesterday": {
        "primary": ["news", "sigint", "socmint"],
        "secondary": [],
    },
    "next_24h_outlook": {
        "primary": ["scenarios", "cyber", "socmint", "diplo", "sigint"],
        "secondary": ["chokepoint", "finint"],
    },
    "source_check": {"primary": [], "secondary": []},
}


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
    if any(
        k in q
        for k in (
            "since yesterday",
            "since last",
            "changed",
            "change",
            "new today",
            "what changed",
            "seit gestern",
            "seit heute",
            "was hat sich geändert",
            "änderung",
            "veraenderung",
        )
    ):
        return "changes_since_yesterday"
    if any(
        k in q
        for k in (
            "risk",
            "danger",
            "threat",
            "escalation",
            "severity",
            "safe",
            "risiko",
            "bedrohung",
            "eskalation",
            "gefähr",
            "gefahr",
        )
    ):
        return "risk_assessment"
    if any(
        k in q
        for k in (
            "next 24h",
            "next 24",
            "next day",
            "tomorrow",
            "outlook",
            "forecast",
            "nächsten 24",
            "naechsten 24",
            "morgen",
            "ausblick",
            "prognose",
        )
    ):
        return "next_24h_outlook"
    if any(
        k in q
        for k in (
            "source",
            "evidence",
            "proof",
            "link",
            "citation",
            "where from",
            "quelle",
            "beleg",
            "nachweis",
            "woher",
        )
    ):
        return "source_check"
    return "situation_overview"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        s = (item or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse((value or "").strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
    return _dedupe([s for s in gathered if _is_http_url(s)])[:MAX_SOURCES]


def _build_context(analysis: Dict[str, Any], fallback_conflict: str) -> str:
    return _build_context_for_type(analysis, fallback_conflict, "situation_overview")


def _short_text(value: Any, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _clip_chunk(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if max_len <= 0:
        return ""
    if len(t) <= max_len:
        return t
    if max_len <= 3:
        return t[:max_len]
    return t[: max_len - 3].rstrip() + "..."


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _filter_recent_news_articles(articles: Any, since: datetime) -> List[Dict[str, Any]]:
    """Keep articles with published_at >= since; keep items without parseable time (best effort)."""
    if not isinstance(articles, list):
        return []
    out: List[Dict[str, Any]] = []
    for art in articles:
        if not isinstance(art, dict):
            continue
        raw = art.get("published_at") or art.get("publishedAt")
        dt = _parse_iso_datetime(raw)
        if dt is None:
            out.append(art)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        if dt >= since:
            out.append(art)
    return out


def _sigint_block_recent_enough(block: Dict[str, Any], since: datetime) -> bool:
    meta = block.get("_meta")
    if not isinstance(meta, dict):
        return True
    fa = _parse_iso_datetime(meta.get("fetched_at"))
    if fa is None:
        return True
    if fa.tzinfo is None:
        fa = fa.replace(tzinfo=timezone.utc)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return fa >= since


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


def _extract_agent_block(
    agent_key: str,
    block: Any,
    *,
    max_chars: int = 800,
    question_type: Optional[QuestionType] = None,
) -> str:
    if not isinstance(block, dict):
        return ""
    lines: List[str] = []
    since = datetime.now(timezone.utc) - timedelta(hours=CHANGES_RECENT_HOURS)

    if agent_key == "sigint" and question_type == "changes_since_yesterday" and not _sigint_block_recent_enough(block, since):
        lines.append("SIGINT note: cached snapshot may be older than the recency window; treat as non-fresh.")

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
        articles: Any = block.get("articles")
        if question_type == "changes_since_yesterday":
            articles = _filter_recent_news_articles(articles, since)
        lines.extend(_dict_items_as_text(_slice_items(articles, 5), ["title", "source", "sentiment", "url"], 5))
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

    return _clip_chunk("\n".join(lines).strip(), max_chars)


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


def _extract_cyber_greynoise_focus(block: Any, *, max_chars: int = 800) -> str:
    """Narrow CYBER excerpt for next_24h_outlook: summary + GreyNoise scan rows only (saves tokens vs full cyber context)."""
    if not isinstance(block, dict):
        return ""
    lines: List[str] = []
    summary = _short_text(block.get("summary"), 320)
    if summary:
        lines.append(f"CYBER summary: {summary}")
    lines.extend(
        _dict_items_as_text(
            _slice_items(block.get("greynoise_scan_context"), 5),
            ["ip", "classification", "last_seen"],
            5,
        )
    )
    if not lines:
        return ""
    return _clip_chunk("CYBER GREYNOISE (focused):\n" + "\n".join(lines), max_chars)


def _extract_source_check_index(analysis: Dict[str, Any]) -> str:
    """Deduplicated URLs from all agent _meta.sources plus NEWS article URLs; minimal prose."""
    lines: List[str] = []
    seen_urls: Set[str] = set()

    for key, block in analysis.items():
        if not isinstance(block, dict):
            continue
        meta = block.get("_meta")
        if not isinstance(meta, dict):
            continue
        for src in meta.get("sources") or []:
            if not isinstance(src, dict):
                continue
            label = _short_text(src.get("name") or src.get("source") or "", 80)
            for url in src.get("reference_urls") or []:
                if not isinstance(url, str):
                    continue
                u = url.strip()
                if not _is_http_url(u):
                    continue
                lk = u.lower()
                if lk in seen_urls:
                    continue
                seen_urls.add(lk)
                if label:
                    lines.append(f"- [{key}] {label}: {u}")
                else:
                    lines.append(f"- [{key}]: {u}")

    news = analysis.get("news") or {}
    if isinstance(news, dict):
        for art in news.get("articles") or []:
            if not isinstance(art, dict):
                continue
            url = art.get("url")
            if not isinstance(url, str):
                continue
            u = url.strip()
            if not _is_http_url(u):
                continue
            lk = u.lower()
            if lk in seen_urls:
                continue
            seen_urls.add(lk)
            title = _short_text(art.get("title"), 120)
            if title:
                lines.append(f"- [news] {title}: {u}")
            else:
                lines.append(f"- [news]: {u}")

    if not lines:
        return "SOURCE INDEX:\n(no HTTP URLs in cache)"
    return "SOURCE INDEX:\n" + "\n".join(lines)


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
    base = QUESTION_TYPE_AGENTS.get(question_type) or QUESTION_TYPE_AGENTS["situation_overview"]
    primary = list(base.get("primary") or [])
    secondary = list(base.get("secondary") or [])

    if question_type == "changes_since_yesterday":
        prim_set = set(primary)
        secondary_agents = [
            k
            for k in analysis.keys()
            if k not in prim_set
            and isinstance(analysis.get(k), dict)
            and (analysis.get(k) or {}).get("summary")
        ]
        secondary = secondary + secondary_agents

    if question_type == "source_check":
        primary = [k for k, v in analysis.items() if isinstance(v, dict) and _has_reference_urls(v)]
        secondary = ["news"] if isinstance(analysis.get("news"), dict) else []

    return {"primary": primary, "secondary": secondary}


def _diff_specific_has_signal(spec: Any) -> bool:
    if not isinstance(spec, dict) or not spec:
        return False
    for _k, v in spec.items():
        if isinstance(v, int) and v != 0:
            return True
        if isinstance(v, float) and v != 0.0:
            return True
        if isinstance(v, list) and len(v) > 0:
            return True
    return False


def _format_diff_for_chat(diff: Dict[str, Any], *, max_chars: int) -> str:
    """Compact, LLM-friendly text from Layer 4 diff_runs output."""
    lines: List[str] = []
    lines.append(f"Compared runs: previous={diff.get('run_id_prev')} current={diff.get('run_id_curr')}")
    summ = diff.get("summary") or {}
    lines.append(
        f"Snapshot summary: {summ.get('agents_changed', 0)} agent block(s) changed of {summ.get('agents_total', 0)} total."
    )
    g = diff.get("global") or {}
    if g.get("escalation_score_delta") is not None:
        lines.append(
            f"Escalation (FININT block): {g.get('escalation_score_prev')} -> {g.get('escalation_score_curr')} "
            f"(delta {g.get('escalation_score_delta')})"
        )
    elif g.get("escalation_score_curr") is not None:
        lines.append(f"Escalation (FININT block) current: {g.get('escalation_score_curr')}")
    tp, tc = g.get("threat_level_prev"), g.get("threat_level_curr")
    if tp or tc:
        lines.append(f"Threat level (FININT block): {tp!s} -> {tc!s}")
    added = g.get("key_findings_added") or []
    resolved = g.get("key_findings_resolved") or []
    if added:
        lines.append("Key findings added since previous run:")
        for f in added[:15]:
            lines.append(f"  + {_short_text(str(f), 300)}")
    if resolved:
        lines.append("Key findings no longer present (resolved/dropped vs previous run):")
        for f in resolved[:10]:
            lines.append(f"  - {_short_text(str(f), 300)}")

    agents = diff.get("agents") or {}
    lines.append("Per-agent deltas (deterministic rules):")
    for name in sorted(agents.keys()):
        ad = agents[name]
        if not isinstance(ad, dict):
            continue
        gen = ad.get("generic") if isinstance(ad.get("generic"), dict) else {}
        spec = ad.get("specific") if isinstance(ad.get("specific"), dict) else {}
        hash_changed = bool(ad.get("content_hash_changed"))
        sd = gen.get("score_delta")
        sig = _diff_specific_has_signal(spec)
        score_moved = isinstance(sd, (int, float)) and abs(float(sd)) >= 0.01
        if not hash_changed and not score_moved and not sig:
            continue
        parts: List[str] = []
        if hash_changed:
            parts.append("content_changed")
        if sd is not None and (score_moved or hash_changed):
            parts.append(f"score_delta={sd}")
        if spec:
            parts.append(f"specific={json.dumps(spec, default=str)[:400]}")
        lines.append(f"  [{name}] " + "; ".join(parts))

    return _clip_chunk("\n".join(lines), max_chars)


def _build_deterministic_changes_context(conflict: str, tenant_id: str) -> str:
    """
    Layer 4 diff between the two latest persisted analysis runs (same conflict, same tenant).
    Empty string if fewer than two runs or diff unavailable.
    """
    try:
        from services.diff_engine import auto_pick_runs_for_diff, diff_runs

        picked = auto_pick_runs_for_diff(conflict=conflict, tenant_id=tenant_id)
        if not picked:
            return ""
        out = diff_runs(
            conflict=conflict,
            run_id_prev=picked["run_id_prev"],
            run_id_curr=picked["run_id_curr"],
            tenant_id=tenant_id,
        )
        if out.get("error"):
            return ""
        block = _format_diff_for_chat(out, max_chars=CHAT_DIFF_CONTEXT_MAX_CHARS)
        if not block.strip():
            return ""
        return (
            "=== DETERMINISTIC RUN-TO-RUN DELTA (Layer 4; use as primary evidence for what changed) ===\n"
            + block
            + "\n=== END DELTA ===\n"
            "=== Current cached snapshot excerpts below (secondary detail) ==="
        )
    except Exception as e:
        _chat_logger.debug("deterministic changes context failed: %s", e)
        return ""


def _build_context_for_type(
    analysis: Dict[str, Any],
    fallback_conflict: str,
    question_type: QuestionType,
    *,
    tenant_id: Optional[str] = None,
) -> str:
    conflict = str(analysis.get("conflict") or fallback_conflict)
    escalation = analysis.get("escalation_score")
    threat = analysis.get("threat_level")
    summary = _short_text(analysis.get("summary"), 600)
    findings = [str(f) for f in (analysis.get("key_findings") or []) if isinstance(f, str)][:8]

    if question_type == "source_check":
        header_lines = [
            f"Conflict: {conflict}",
            f"Question type: {question_type}",
            "Use the following provenance index (URLs from cached agents). Prefer citing these over paraphrase.",
        ]
        header = "\n".join(header_lines).strip()
        idx = _extract_source_check_index(analysis)
        combined = f"{header}\n\n{_clip_chunk(idx, max(CONTEXT_CHAR_BUDGET - len(header) - 2, 0))}"
        return _clip_chunk(combined, CONTEXT_CHAR_BUDGET)

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

    diff_prefix = ""
    if question_type == "changes_since_yesterday" and tenant_id:
        diff_prefix = _build_deterministic_changes_context(conflict, tenant_id)
        if diff_prefix:
            diff_prefix = diff_prefix.strip() + "\n\n"

    plan = _question_context_plan(question_type, analysis)
    body_chunks: List[str] = []
    seen_keys: Set[str] = set()
    base_len = len(header) + len(diff_prefix) + 2
    remaining = max(CONTEXT_CHAR_BUDGET - base_len, 0)

    def add_body(text: str) -> None:
        nonlocal remaining
        if remaining <= 0:
            return
        cap = min(AGENT_CHUNK_MAX_CHARS, remaining)
        clipped = _clip_chunk(text, cap)
        if not clipped:
            return
        body_chunks.append(clipped)
        remaining -= len(clipped) + 2

    def agent_chunk(agent_key: str) -> str:
        cap = min(AGENT_CHUNK_MAX_CHARS, max(remaining, 0))
        if agent_key == "cyber" and question_type == "next_24h_outlook":
            return _extract_cyber_greynoise_focus(analysis.get("cyber"), max_chars=cap)
        return _extract_agent_block(
            agent_key,
            analysis.get(agent_key),
            max_chars=cap,
            question_type=question_type,
        )

    for key in plan.get("primary", []):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key == "compliance":
            add_body(_extract_compliance_context(analysis))
            continue
        if key == "scenarios":
            add_body(_extract_scenarios_context(analysis))
            continue
        add_body(agent_chunk(key))

    for key in plan.get("secondary", []):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key == "compliance":
            add_body(_extract_compliance_context(analysis))
            continue
        if key == "scenarios":
            add_body(_extract_scenarios_context(analysis))
            continue
        add_body(agent_chunk(key))

    if diff_prefix and not body_chunks:
        return _clip_chunk(header + "\n\n" + diff_prefix, CONTEXT_CHAR_BUDGET)
    if not body_chunks:
        return _clip_chunk(header, CONTEXT_CHAR_BUDGET)
    out = header + "\n\n" + diff_prefix + "\n\n".join(body_chunks)
    return _clip_chunk(out, CONTEXT_CHAR_BUDGET)


def _fallback_agent_sources(question_type: QuestionType, analysis: Dict[str, Any]) -> List[str]:
    labels = {
        "situation_overview": [
            "NEWS analysis",
            "GEOINT analysis",
            "DIPLO sanctions track",
            "SIGINT monitoring",
            "NARRATIVE synthesis",
        ],
        "risk_assessment": [
            "COMPLIANCE risk model",
            "FININT indicators",
            "CYBER indicators",
            "CHOKEPOINT indicators",
            "SOCMINT civil-unrest proxy",
        ],
        "changes_since_yesterday": [
            "NEWS updates",
            "SIGINT monitoring",
            "SOCMINT civil-unrest proxy",
        ],
        "next_24h_outlook": [
            "SCENARIO projection",
            "CYBER GREYNOISE focus",
            "SOCMINT civil-unrest proxy",
            "DIPLO sanctions track",
            "SIGINT monitoring",
        ],
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


LIVE_ENRICHMENT_TIMEOUT = 8.0
_GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_RELIEFWEB_API_URL = "https://api.reliefweb.int/v2/reports"
_RELIEFWEB_COUNTRIES: Dict[str, str] = {
    "iran": "Iran",
    "israel": "Israel",
    "gaza": "State of Palestine",
    "yemen": "Yemen",
    "lebanon": "Lebanon",
    "syria": "Syria",
    "iraq": "Iraq",
    "ukraine": "Ukraine",
    "russia": "Russian Federation",
}


def _gdelt_query(conflict: str) -> str:
    cl = conflict.lower()
    if "iran" in cl or "israel" in cl:
        return "Iran Israel Gaza IRGC"
    if "ukraine" in cl or "russia" in cl:
        return "Ukraine Russia Donbas"
    if "yemen" in cl:
        return "Yemen Houthi Red Sea"
    if "syria" in cl:
        return "Syria Damascus Idlib"
    if "lebanon" in cl:
        return "Lebanon Hezbollah Beirut"
    cleaned = " ".join(re.findall(r"[A-Za-z0-9]{2,}", conflict or ""))[:80]
    return cleaned or "conflict"


async def _fetch_gdelt_articles(conflict: str) -> List[Dict[str, str]]:
    """Quick GDELT DOC artlist fetch — returns up to 10 article dicts with title/url."""
    query = _gdelt_query(conflict)
    try:
        async with httpx.AsyncClient(timeout=LIVE_ENRICHMENT_TIMEOUT) as client:
            resp = await client.get(
                _GDELT_DOC_URL,
                params={"query": query, "mode": "artlist", "format": "json", "maxrecords": 20, "timespan": "48H"},
            )
            if resp.status_code != 200:
                return []
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct and "javascript" not in ct:
                return []
            data = resp.json() if resp.text else {}
            raw_articles = data.get("articles") if isinstance(data, dict) else (data if isinstance(data, list) else [])
            out: List[Dict[str, str]] = []
            for art in (raw_articles or [])[:10]:
                if not isinstance(art, dict):
                    continue
                title = str(art.get("title") or "").strip()[:200]
                url = str(art.get("url") or "").strip()
                domain = str(art.get("domain") or "").strip()
                if title:
                    out.append({"title": title, "url": url, "source": domain})
            return out
    except Exception as exc:
        _chat_logger.debug("Chat live GDELT fetch failed: %s", exc)
        return []


async def _fetch_reliefweb_headlines(conflict: str) -> List[Dict[str, str]]:
    """Quick ReliefWeb API v2 fetch — returns up to 8 report dicts with title/url."""
    cl = conflict.lower()
    country = next((v for k, v in _RELIEFWEB_COUNTRIES.items() if k in cl), "Iran")
    try:
        async with httpx.AsyncClient(timeout=LIVE_ENRICHMENT_TIMEOUT) as client:
            resp = await client.get(
                _RELIEFWEB_API_URL,
                params={
                    "appname": "digital-war-room",
                    "limit": 8,
                    "filter[field]": "country",
                    "filter[value]": country,
                    "preset": "latest",
                    "fields[include][]": ["title", "url", "source.name"],
                },
                headers={"User-Agent": "Mozilla/5.0 (compatible; DWR-Chat/1.0)"},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            out: List[Dict[str, str]] = []
            for item in (items or [])[:8]:
                if not isinstance(item, dict):
                    continue
                fields = item.get("fields") or {}
                title = str(fields.get("title") or "").strip()[:200]
                url_raw = fields.get("url", "")
                url = url_raw if isinstance(url_raw, str) else ""
                src_list = fields.get("source") or []
                source = src_list[0].get("name", "ReliefWeb") if src_list and isinstance(src_list[0], dict) else "ReliefWeb"
                if title:
                    out.append({"title": title, "url": url.strip(), "source": source})
            return out
    except Exception as exc:
        _chat_logger.debug("Chat live ReliefWeb fetch failed: %s", exc)
        return []


async def _enrich_context_live(conflict: str) -> tuple:
    """
    Lightweight live data fetch (GDELT + ReliefWeb) for when cached context
    is thin or absent.  Returns (context_str, source_urls).
    """
    gdelt_task = asyncio.create_task(_fetch_gdelt_articles(conflict))
    rw_task = asyncio.create_task(_fetch_reliefweb_headlines(conflict))
    gdelt_articles, rw_reports = await asyncio.gather(gdelt_task, rw_task, return_exceptions=True)
    if isinstance(gdelt_articles, BaseException):
        gdelt_articles = []
    if isinstance(rw_reports, BaseException):
        rw_reports = []

    lines: List[str] = []
    urls: List[str] = []

    if gdelt_articles:
        lines.append("LIVE NEWS (GDELT):")
        for art in gdelt_articles[:8]:
            lines.append(f"- {art['title']} ({art.get('source', '')})")
            if art.get("url") and _is_http_url(art["url"]):
                urls.append(art["url"])

    if rw_reports:
        lines.append("LIVE REPORTS (ReliefWeb):")
        for rpt in rw_reports[:6]:
            lines.append(f"- {rpt['title']} ({rpt.get('source', '')})")
            if rpt.get("url") and _is_http_url(rpt["url"]):
                urls.append(rpt["url"])

    context = "\n".join(lines)
    return context, _dedupe(urls)[:MAX_SOURCES]


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


def _build_low_confidence_answer(answer: str, question_type: QuestionType) -> str:
    prefix = (
        "Evidence is currently limited in cache, so this answer may be incomplete. "
        "Treat it as an early signal and verify with new incoming sources."
    )
    if question_type == "source_check":
        prefix = (
            "Source evidence is currently sparse in cache, so this answer is only a partial check. "
            "Treat it as provisional and validate with fresh references."
        )
    return f"{prefix}\n\n{answer.strip()}"


@router.post("/chat/ask")
@limiter.limit("20/minute")
async def chat_ask(request: Request, state: StateServiceDep, body: ChatAskRequest) -> ChatAskResponse:
    question = body.question.strip()
    conflict = body.conflict or DEFAULT_CONFLICT
    response_id = str(uuid.uuid4())
    question_type = _detect_question_type(question)
    tenant_id = str(get_request_ctx(request).tenant_id)
    cached = state.get_cache(conflict, tenant_id=tenant_id)
    analysis: Dict[str, Any] = {}
    if cached and isinstance(cached.get("result"), dict):
        analysis = cached["result"]

    context = (
        _build_context_for_type(analysis, conflict, question_type, tenant_id=tenant_id) if analysis else ""
    )
    sources = _collect_sources(analysis) if analysis else []

    MIN_CONTEXT_LEN = 200
    if len(context) < MIN_CONTEXT_LEN:
        live_ctx, live_urls = await _enrich_context_live(conflict)
        if live_ctx:
            context = (context + "\n\n" + live_ctx).strip() if context else live_ctx
        if live_urls:
            sources = _dedupe(sources + live_urls)[:MAX_SOURCES]

    system = (
        "You are a geopolitical analyst assistant for a dashboard chat MVP.\n"
        "Answer strictly in English, based only on provided context.\n"
        "Never fabricate facts or sources.\n"
        "If context contains any relevant signals, always attempt an answer.\n"
        "Prefer a partial answer with caveats over refusing to answer.\n"
        "Confidence calibration:\n"
        "- >=0.70: grounded in multiple context signals.\n"
        "- 0.50-0.69: grounded but limited to partial or single-source context.\n"
        "- 0.30-0.49: plausible inference from context with uncertainty.\n"
        "- 0.10-0.29: limited context but some relevant data points exist.\n"
        "- <0.10: context truly empty or irrelevant.\n"
        "Answer format: 1-3 sentence lead, then concise bullet points when useful.\n"
        "Return only valid JSON with keys: answer, confidence_score, sources.\n"
        "confidence_score must be a float between 0 and 1.\n"
        "sources must be an array of strings — use URLs when available, "
        "otherwise use descriptive labels like 'FININT market data' or 'GDELT news monitoring'.\n"
        'Example: {"answer":"Risk remains elevated due to maritime and sanctions pressure.","confidence_score":0.64,"sources":["https://example.com/report","FININT market data"]}'
    )
    user_content = (
        f"Question type: {question_type}\n"
        f"Question: {question}\n\n"
        f"Context:\n{context}\n\n"
        f"Candidate sources:\n{json.dumps(sources)}\n"
    )
    raw = await analyst_summary(
        system=system,
        data=user_content,
        max_tokens=CHAT_MAX_TOKENS,
        usage_agent="analyst",
        model=None,
        skip_run_limits=True,
    )
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
    llm_sources = _dedupe([str(s).strip() for s in out_sources_raw if isinstance(s, str)])[:MAX_SOURCES] if isinstance(out_sources_raw, list) else []
    if not llm_sources:
        llm_sources = sources[:MAX_SOURCES]
    out_sources = [s for s in llm_sources if _is_http_url(s)]
    if not out_sources:
        non_url_labels = [s for s in llm_sources if s and not _is_http_url(s)]
        agent_labels = _fallback_agent_sources(question_type, analysis)
        out_sources = _dedupe(non_url_labels + agent_labels)[:MAX_SOURCES]

    requires_sources = question_type == "source_check" or confidence >= SOURCE_REQUIRED_CONFIDENCE
    missing_required_sources = requires_sources and question_type not in SOURCE_FREE_QUESTION_TYPES and len(out_sources) == 0
    if not answer or confidence < LOW_CONFIDENCE_FLOOR or (question_type == "source_check" and missing_required_sources):
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

    if confidence < CONFIDENCE_MIN or (missing_required_sources and confidence < SOURCE_REQUIRED_CONFIDENCE):
        response = ChatAskResponse(
            response_id=response_id,
            question_type=question_type,
            answer=_build_low_confidence_answer(answer, question_type),
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
        "fallback_used": bool(resolved.get("fallback_used")),
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
