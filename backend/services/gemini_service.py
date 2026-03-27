"""Native Gemini Developer API client with per-run budget enforcement."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from agents.research_contracts import ResearchBudgetStatus, ResearchRunBudget, ResearchUsage

logger = logging.getLogger(__name__)

GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
GEMINI_MODEL = os.getenv("RESEARCH_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SEC = float(os.getenv("RESEARCH_GEMINI_TIMEOUT_SEC", "20"))

# USD / 1M tokens (defaults for Gemini 2.5 Flash standard tier)
GEMINI_INPUT_USD_PER_MTOK = float(os.getenv("RESEARCH_GEMINI_INPUT_USD_PER_MTOK", "0.30"))
GEMINI_OUTPUT_USD_PER_MTOK = float(os.getenv("RESEARCH_GEMINI_OUTPUT_USD_PER_MTOK", "2.50"))

RESEARCH_MAX_REQUESTS_PER_RUN = int(os.getenv("RESEARCH_MAX_REQUESTS_PER_RUN", "1"))
RESEARCH_MAX_INPUT_TOKENS_PER_RUN = int(os.getenv("RESEARCH_MAX_INPUT_TOKENS_PER_RUN", "12000"))
RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN = int(os.getenv("RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN", "3000"))
RESEARCH_MAX_COST_USD_PER_RUN = float(os.getenv("RESEARCH_MAX_COST_USD_PER_RUN", "0.08"))


def default_research_budget() -> ResearchRunBudget:
    return ResearchRunBudget(
        max_requests_per_run=RESEARCH_MAX_REQUESTS_PER_RUN,
        max_input_tokens_per_run=RESEARCH_MAX_INPUT_TOKENS_PER_RUN,
        max_output_tokens_per_run=RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN,
        max_cost_usd_per_run=RESEARCH_MAX_COST_USD_PER_RUN,
    )


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (float(input_tokens) / 1_000_000.0) * GEMINI_INPUT_USD_PER_MTOK + (
        float(output_tokens) / 1_000_000.0
    ) * GEMINI_OUTPUT_USD_PER_MTOK


def evaluate_budget(usage: ResearchUsage, budget: ResearchRunBudget) -> ResearchBudgetStatus:
    blocked_reason: Optional[str] = None
    if usage.requests >= budget.max_requests_per_run:
        blocked_reason = "max_requests_per_run_exceeded"
    elif budget.max_input_tokens_per_run > 0 and usage.input_tokens >= budget.max_input_tokens_per_run:
        blocked_reason = "max_input_tokens_per_run_exceeded"
    elif budget.max_output_tokens_per_run > 0 and usage.output_tokens >= budget.max_output_tokens_per_run:
        blocked_reason = "max_output_tokens_per_run_exceeded"
    elif budget.max_cost_usd_per_run > 0 and usage.estimated_cost_usd >= budget.max_cost_usd_per_run:
        blocked_reason = "max_cost_usd_per_run_exceeded"
    return ResearchBudgetStatus(allowed=blocked_reason is None, blocked_reason=blocked_reason, budget=budget, usage=usage)


@dataclass
class GeminiResearchResponse:
    ok: bool
    raw_text: str
    parsed_json: Optional[Dict[str, Any]]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None


@dataclass
class GeminiTextResponse:
    ok: bool
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None


def _extract_text(payload: Dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content") if isinstance(first, dict) else {}
    parts = content.get("parts") if isinstance(content, dict) else []
    chunks = []
    for p in parts if isinstance(parts, list) else []:
        if isinstance(p, dict) and isinstance(p.get("text"), str):
            chunks.append(p["text"])
    return "\n".join(chunks).strip()


def _parse_json_text(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_usage(payload: Dict[str, Any]) -> Tuple[int, int]:
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return 0, 0
    inp = usage.get("promptTokenCount")
    out = usage.get("candidatesTokenCount")
    try:
        return int(inp or 0), int(out or 0)
    except Exception:
        return 0, 0


def run_gemini_research(prompt: str) -> GeminiResearchResponse:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return GeminiResearchResponse(
            ok=False,
            raw_text="",
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error="missing_gemini_api_key",
        )

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }

    try:
        with httpx.Client(timeout=GEMINI_TIMEOUT_SEC) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Gemini research call failed: %s", exc)
        return GeminiResearchResponse(
            ok=False,
            raw_text="",
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=f"request_failed:{type(exc).__name__}",
        )

    text = _extract_text(data)
    parsed = _parse_json_text(text)
    input_tokens, output_tokens = _extract_usage(data)
    cost = estimate_cost_usd(input_tokens, output_tokens)
    return GeminiResearchResponse(
        ok=True,
        raw_text=text,
        parsed_json=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if parsed is not None else "invalid_json_response",
    )


def run_gemini_text(prompt: str) -> GeminiTextResponse:
    """Run Gemini and return plain text output."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return GeminiTextResponse(
            ok=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error="missing_gemini_api_key",
        )

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "text/plain"},
    }

    try:
        with httpx.Client(timeout=GEMINI_TIMEOUT_SEC) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Gemini text call failed: %s", exc)
        return GeminiTextResponse(
            ok=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=f"request_failed:{type(exc).__name__}",
        )

    text = _extract_text(data)
    input_tokens, output_tokens = _extract_usage(data)
    cost = estimate_cost_usd(input_tokens, output_tokens)
    return GeminiTextResponse(
        ok=bool(text),
        text=text.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if text else "empty_text_response",
    )
