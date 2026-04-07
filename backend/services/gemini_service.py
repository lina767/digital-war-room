"""Native Gemini Developer API client with per-run budget enforcement."""

from __future__ import annotations

import json
import logging
import os
import base64
import time
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from agents.research_contracts import ResearchBudgetStatus, ResearchRunBudget, ResearchUsage
from services.http_client import CircuitOpenError, get_http_client

logger = logging.getLogger(__name__)

GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
GEMINI_MODEL = os.getenv("RESEARCH_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = (os.getenv("RESEARCH_GEMINI_FALLBACK_MODEL") or "").strip()
GEMINI_TIMEOUT_SEC = float(os.getenv("RESEARCH_GEMINI_TIMEOUT_SEC", "20"))
GEMINI_MAX_RETRIES = max(0, int(os.getenv("RESEARCH_GEMINI_MAX_RETRIES", "2")))
GEMINI_RETRY_BASE_DELAY_SEC = max(0.1, float(os.getenv("RESEARCH_GEMINI_RETRY_BASE_DELAY_SEC", "1.0")))
GEMINI_RETRY_MAX_DELAY_SEC = max(0.5, float(os.getenv("RESEARCH_GEMINI_RETRY_MAX_DELAY_SEC", "8.0")))

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


@dataclass
class GeminiVisionResponse:
    ok: bool
    parsed_json: Optional[Dict[str, Any]]
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


def _gemini_url(api_key: str, model: str) -> str:
    return f"{GEMINI_API_BASE}/models/{model}:generateContent?key={api_key}"


def _model_candidates() -> list[str]:
    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)
    return models


def _post_with_retries(
    *,
    api_key: str,
    payload: Dict[str, Any],
    call_kind: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """POST to Gemini with shared resilient client and optional fallback model."""
    last_error: Optional[str] = None
    for model in _model_candidates():
        url = _gemini_url(api_key, model)
        try:
            data = asyncio.run(
                _post_with_shared_client_async(
                    url=url,
                    payload=payload,
                )
            )
            if data is not None:
                return data, None
            last_error = "invalid_json_response"
        except RuntimeError:
            # Fallback path if called inside an already running event loop.
            try:
                with httpx.Client(timeout=GEMINI_TIMEOUT_SEC) as client:
                    resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    try:
                        return resp.json(), None
                    except Exception:
                        return None, "invalid_json_response"
                body = (resp.text or "")[:240]
                last_error = f"http_{resp.status_code}:{body}"
            except Exception as exc:
                last_error = f"request_failed:{type(exc).__name__}"
        except CircuitOpenError:
            last_error = "request_failed:CircuitOpenError"
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:240]
            last_error = f"http_{exc.response.status_code}:{body}"
        except Exception as exc:
            last_error = f"request_failed:{type(exc).__name__}"

        if model != GEMINI_MODEL:
            logger.info("Gemini %s call used fallback model: %s", call_kind, model)
        elif GEMINI_FALLBACK_MODEL and last_error and last_error.startswith("http_429"):
            logger.warning("Gemini %s rate-limited on %s, trying fallback model %s", call_kind, GEMINI_MODEL, GEMINI_FALLBACK_MODEL)

    return None, last_error or "request_failed:unknown"


async def _post_with_shared_client_async(*, url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    client = get_http_client()
    resp = await client.request(
        "POST",
        url,
        json=payload,
        timeout=GEMINI_TIMEOUT_SEC,
        retries=GEMINI_MAX_RETRIES,
        backoff_base=GEMINI_RETRY_BASE_DELAY_SEC,
        retry_statuses={429, 500, 502, 503, 504},
        service_name="gemini_api",
        recovery_timeout_sec=GEMINI_RETRY_MAX_DELAY_SEC,
    )
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


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

    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }

    data, err = _post_with_retries(api_key=api_key, payload=payload, call_kind="research")
    if not data:
        logger.warning("Gemini research call failed: %s", err or "unknown_error")
        return GeminiResearchResponse(
            ok=False,
            raw_text="",
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=err or "request_failed:unknown",
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

    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "text/plain"},
    }

    data, err = _post_with_retries(api_key=api_key, payload=payload, call_kind="text")
    if not data:
        logger.warning("Gemini text call failed: %s", err or "unknown_error")
        return GeminiTextResponse(
            ok=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=err or "request_failed:unknown",
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


def run_gemini_vision_json(prompt: str, image_bytes: bytes, mime_type: str = "image/png") -> GeminiVisionResponse:
    """Run Gemini multimodal request (prompt + inline image) expecting JSON output."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return GeminiVisionResponse(
            ok=False,
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error="missing_gemini_api_key",
        )
    if not image_bytes:
        return GeminiVisionResponse(
            ok=False,
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error="missing_image_bytes",
        )

    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload: Dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": encoded}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    data, err = _post_with_retries(api_key=api_key, payload=payload, call_kind="vision")
    if not data:
        logger.warning("Gemini vision call failed: %s", err or "unknown_error")
        return GeminiVisionResponse(
            ok=False,
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=err or "request_failed:unknown",
        )
    text = _extract_text(data)
    parsed = _parse_json_text(text)
    input_tokens, output_tokens = _extract_usage(data)
    cost = estimate_cost_usd(input_tokens, output_tokens)
    return GeminiVisionResponse(
        ok=parsed is not None,
        parsed_json=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if parsed is not None else "invalid_json_response",
    )
