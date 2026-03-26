"""
Google web SERP snapshots for monitoring (SerpAPI).

One search = one billable SerpAPI call. Uses separate hourly/monthly caps from
PENTAGON_SIGNALS (see MONITORING_GOOGLE_SERPAPI_*). Query text follows the same
ranking-query resolution as HF cross-encoder (_get_ranking_query).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from services.http_client import get_http_client

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
QUOTA_FILE = Path(__file__).resolve().parent.parent / "data" / "monitoring_google_serp_quota.json"
_QUOTA_LOCK = threading.Lock()


def _env_true(key: str, default: bool = False) -> bool:
    val = (os.getenv(key) or "").strip().lower()
    if default and not val:
        return True
    return val in ("1", "true", "yes")


def _monitoring_serp_limits() -> Tuple[int, int]:
    hourly = int(os.getenv("MONITORING_GOOGLE_SERPAPI_HOURLY_CAP", "30") or "30")
    monthly = int(os.getenv("MONITORING_GOOGLE_SERPAPI_MONTHLY_CAP", "150") or "150")
    return max(0, hourly), max(0, monthly)


def _hour_bucket_utc(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H")


def _month_bucket_utc(now: datetime) -> str:
    return now.strftime("%Y-%m")


def _load_quota_state() -> Dict[str, Any]:
    if not QUOTA_FILE.exists():
        return {"hour_bucket": "", "hour_count": 0, "month_bucket": "", "month_count": 0}
    try:
        raw = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("quota file not dict")
        return {
            "hour_bucket": str(raw.get("hour_bucket") or ""),
            "hour_count": int(raw.get("hour_count") or 0),
            "month_bucket": str(raw.get("month_bucket") or ""),
            "month_count": int(raw.get("month_count") or 0),
        }
    except Exception:
        return {"hour_bucket": "", "hour_count": 0, "month_bucket": "", "month_count": 0}


def _save_quota_state(state: Dict[str, Any]) -> None:
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(state, ensure_ascii=True), encoding="utf-8")


def _quota_try_consume(needed: int) -> Tuple[bool, Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    hour_bucket = _hour_bucket_utc(now)
    month_bucket = _month_bucket_utc(now)
    hourly_cap, monthly_cap = _monitoring_serp_limits()

    with _QUOTA_LOCK:
        state = _load_quota_state()
        hour_count = int(state.get("hour_count") or 0)
        month_count = int(state.get("month_count") or 0)
        if str(state.get("hour_bucket") or "") != hour_bucket:
            hour_count = 0
        if str(state.get("month_bucket") or "") != month_bucket:
            month_count = 0

        allowed = (hour_count + needed <= hourly_cap) and (month_count + needed <= monthly_cap)
        snapshot = {
            "hour_bucket": hour_bucket,
            "hour_count": hour_count,
            "hourly_cap": hourly_cap,
            "month_bucket": month_bucket,
            "month_count": month_count,
            "monthly_cap": monthly_cap,
            "needed": needed,
        }
        if not allowed:
            return False, snapshot

        new_state = {
            "hour_bucket": hour_bucket,
            "hour_count": hour_count + needed,
            "month_bucket": month_bucket,
            "month_count": month_count + needed,
        }
        _save_quota_state(new_state)
        snapshot["hour_count"] = new_state["hour_count"]
        snapshot["month_count"] = new_state["month_count"]
        return True, snapshot


def get_quota_snapshot_readonly() -> Dict[str, Any]:
    """Current counters without consuming (for UI)."""
    now = datetime.now(timezone.utc)
    hour_bucket = _hour_bucket_utc(now)
    month_bucket = _month_bucket_utc(now)
    hourly_cap, monthly_cap = _monitoring_serp_limits()
    with _QUOTA_LOCK:
        state = _load_quota_state()
        hour_count = int(state.get("hour_count") or 0)
        month_count = int(state.get("month_count") or 0)
        if str(state.get("hour_bucket") or "") != hour_bucket:
            hour_count = 0
        if str(state.get("month_bucket") or "") != month_bucket:
            month_count = 0
        return {
            "hour_bucket": hour_bucket,
            "hour_count": hour_count,
            "hourly_cap": hourly_cap,
            "month_bucket": month_bucket,
            "month_count": month_count,
            "monthly_cap": monthly_cap,
        }


def _parse_organic(payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    raw = payload.get("organic_results")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in raw[:limit]:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        link = row.get("link")
        snippet = row.get("snippet") or row.get("snippet_highlighted_words")
        if isinstance(snippet, list):
            snippet = " ".join(str(x) for x in snippet[:6])
        pos = row.get("position")
        out.append(
            {
                "title": str(title)[:300] if title else "",
                "link": str(link)[:2000] if link else "",
                "snippet": str(snippet)[:800] if snippet else "",
                "position": int(pos) if isinstance(pos, int) else None,
            }
        )
    return out


async def fetch_google_trend_snapshot(*, conflict: str, query: str) -> Dict[str, Any]:
    """
    Perform one Google web search via SerpAPI. Consumes quota only after a successful
    reservation and before HTTP call. On HTTP/parse failure, quota is already consumed
    (same as pentagon agent — avoids abuse; caps are conservative).
    """
    if not _env_true("MONITORING_GOOGLE_SERP_ENABLED", default=True):
        return {
            "ok": False,
            "error": "disabled",
            "message": "MONITORING_GOOGLE_SERP_ENABLED is false.",
            "conflict": conflict,
            "query": query,
            "quota": get_quota_snapshot_readonly(),
        }

    api_key = (os.getenv("SERPAPI_KEY") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "missing SERPAPI_KEY",
            "message": "Set SERPAPI_KEY to enable Google trend snapshots.",
            "conflict": conflict,
            "query": query,
            "quota": get_quota_snapshot_readonly(),
        }

    allowed, quota = _quota_try_consume(1)
    if not allowed:
        return {
            "ok": False,
            "error": "serpapi_quota_capped",
            "message": (
                f"Monitoring SerpAPI cap reached: {quota.get('hour_count', 0)}/{quota.get('hourly_cap', 0)} "
                f"this UTC hour, {quota.get('month_count', 0)}/{quota.get('monthly_cap', 0)} this UTC month."
            ),
            "conflict": conflict,
            "query": query,
            "quota": quota,
        }

    num = int(os.getenv("MONITORING_GOOGLE_SERP_NUM", "8") or "8")
    num = max(3, min(12, num))
    gl = (os.getenv("MONITORING_GOOGLE_SERP_GL") or "").strip()
    hl = (os.getenv("MONITORING_GOOGLE_SERP_HL") or "").strip()
    params: Dict[str, Any] = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": num,
    }
    if gl:
        params["gl"] = gl
    if hl:
        params["hl"] = hl
    url = f"{SERPAPI_URL}?{urlencode(params)}"

    try:
        client = get_http_client()
        payload = await client.get_json(url)
    except Exception as e:
        logger.warning("MONITORING_GOOGLE_SERP: request failed: %s", e)
        return {
            "ok": False,
            "error": "request_failed",
            "message": str(e)[:500],
            "conflict": conflict,
            "query": query,
            "quota": get_quota_snapshot_readonly(),
        }

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_response",
            "message": "SerpAPI returned non-object JSON.",
            "conflict": conflict,
            "query": query,
            "quota": get_quota_snapshot_readonly(),
        }

    serp_err = payload.get("error")
    if serp_err:
        return {
            "ok": False,
            "error": "serpapi_error",
            "message": str(serp_err)[:500],
            "conflict": conflict,
            "query": query,
            "quota": get_quota_snapshot_readonly(),
        }

    organic = _parse_organic(payload, num)
    si = payload.get("search_information")
    search_information: Optional[Dict[str, Any]] = None
    if isinstance(si, dict):
        search_information = {
            k: si.get(k)
            for k in ("total_results", "time_taken_displayed", "query_displayed")
            if k in si
        }

    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "conflict": conflict,
        "query": query,
        "fetched_at": fetched_at,
        "engine": "google",
        "organic": organic,
        "search_information": search_information,
        "quota": get_quota_snapshot_readonly(),
    }
