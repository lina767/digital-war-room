"""
PENTAGON_SIGNALS – Informal DC-area OSINT proxies (Pizza + configurable nightlife).

Uses SerpAPI's Google Maps engine to read popular-times / live busyness for two
configurable venues near the Pentagon. This is explicitly a weak, anecdotal
signal (not verified intelligence); scores are capped and labeled in summaries.

Requires SERPAPI_KEY for live fetches. Without a key (or when disabled), returns
degraded empty signal so CEO weighting does not treat silence as calm.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from services.http_client import get_http_client

from .contracts import get_agent_fallback
from .utils import SourceResult, build_agent_meta, run_async, utc_now_iso

logger = logging.getLogger(__name__)

DC_TZ = ZoneInfo("America/New_York")

# Default search queries (override via env or PENTAGON_SIGNALS_VENUES_JSON)
DEFAULT_VENUES: List[Dict[str, str]] = [
    {
        "role": "pizza",
        "label": "Pizza (Pentagon-area proxy)",
        "query": "Domino's Pizza Pentagon City Arlington VA",
    },
    {
        "role": "nightlife",
        "label": "LGBTQ+ bar / nightlife (Crystal City–Pentagon adjacency, configurable)",
        "query": "Freddie's Beach Bar Crystal City Arlington VA",
    },
]

SERPAPI_URL = "https://serpapi.com/search.json"
QUOTA_FILE = Path(__file__).resolve().parent.parent / "data" / "pentagon_signals_quota.json"
_QUOTA_LOCK = threading.Lock()


def _env_true(key: str, default: bool = False) -> bool:
    val = (os.getenv(key) or "").strip().lower()
    if default and not val:
        return True
    return val in ("1", "true", "yes")


def _load_venues() -> List[Dict[str, str]]:
    raw = (os.getenv("PENTAGON_SIGNALS_VENUES_JSON") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                out: List[Dict[str, str]] = []
                for i, item in enumerate(data):
                    if not isinstance(item, dict):
                        continue
                    q = str(item.get("query") or "").strip()
                    if not q:
                        continue
                    out.append(
                        {
                            "role": str(item.get("role") or f"venue_{i}"),
                            "label": str(item.get("label") or q)[:200],
                            "query": q[:500],
                        }
                    )
                if out:
                    return out
        except json.JSONDecodeError as e:
            logger.warning("PENTAGON_SIGNALS_VENUES_JSON invalid JSON: %s", e)
    return [dict(v) for v in DEFAULT_VENUES]


def _live_text_to_score(text: str) -> float:
    """Map Google's live/popular-times copy to 0–100 (heuristic)."""
    t = (text or "").lower()
    if not t.strip():
        return 0.0
    if "as busy as it gets" in t or "much busier" in t:
        return 92.0
    if "usually busy" in t or "busier than usual" in t:
        return 72.0
    if "usually a little busy" in t or "a little busy" in t:
        return 58.0
    if "usually not too busy" in t or "less busy" in t:
        return 38.0
    if "usually not busy" in t or "not busy" in t:
        return 22.0
    if "closed" in t or "closes soon" in t:
        return 15.0
    if "busy" in t:
        return 65.0
    return 40.0


def _extract_busy_from_place(place: Dict[str, Any]) -> Tuple[float, str]:
    """Return (0–100 score, note) from a SerpAPI/Google Maps place dict."""
    pt = place.get("popular_times")
    if isinstance(pt, dict):
        live = pt.get("live")
        if isinstance(live, str) and live.strip():
            return _live_text_to_score(live), f"live:{live.strip()[:120]}"
        if isinstance(live, dict):
            # Some payloads nest busyness info
            for k in ("description", "text", "status"):
                v = live.get(k)
                if isinstance(v, str) and v.strip():
                    return _live_text_to_score(v), f"live_obj:{str(v)[:120]}"
        graph = pt.get("graph_results") or pt.get("histogram")
        if isinstance(graph, list) and graph:
            now = datetime.now(DC_TZ)
            day_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            today = day_names[now.weekday()]
            hour_key = now.strftime("%I %p").lstrip("0").replace(" 0", " ")
            best: Tuple[float, str] = (0.0, "")
            for row in graph:
                if not isinstance(row, dict):
                    continue
                if str(row.get("day") or "") != today:
                    continue
                info = str(row.get("time") or row.get("hour") or "")
                busyness = row.get("busyness_score") or row.get("percentage") or row.get("busy")
                if isinstance(busyness, (int, float)):
                    sc = float(busyness)
                    if 0.0 <= sc <= 1.0:
                        sc *= 100.0
                    if sc > best[0]:
                        best = (min(100.0, sc), f"graph:{info}:{sc:.0f}")
                elif isinstance(busyness, str) and busyness.strip():
                    s = _live_text_to_score(busyness)
                    if s > best[0]:
                        best = (s, f"graph:{info}:{busyness[:80]}")
            if hour_key and best[0] <= 0:
                # Fallback: first row for today with any info
                for row in graph:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("day") or "") != today:
                        continue
                    raw = row.get("busyness_score") or row.get("info")
                    if isinstance(raw, (int, float)):
                        sc = float(raw) * 100.0 if float(raw) <= 1.0 else float(raw)
                        return min(100.0, sc), f"graph:{row.get('time', '')}"
            if best[0] > 0:
                return best

    # Rare: top-level live string
    live2 = place.get("live")
    if isinstance(live2, str) and live2.strip():
        return _live_text_to_score(live2), f"place_live:{live2.strip()[:120]}"

    return 0.0, "no_popular_times"


async def _serpapi_google_maps(query: str, api_key: str) -> Dict[str, Any]:
    params = {
        "engine": "google_maps",
        "q": query,
        "api_key": api_key,
        "type": "search",
    }
    url = f"{SERPAPI_URL}?{urlencode(params)}"
    client = get_http_client()
    return await client.get_json(url)


def _pick_place_blocks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect place-like dicts from a SerpAPI Google Maps JSON response."""
    out: List[Dict[str, Any]] = []
    for key in ("place_results", "local_results", "organic_results"):
        block = payload.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(block, dict):
            out.append(block)
    return out


def _manual_scores() -> Optional[Dict[str, float]]:
    raw = (os.getenv("PENTAGON_SIGNALS_MANUAL_SCORES") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        pizza = data.get("pizza")
        nightlife = data.get("nightlife")
        out: Dict[str, float] = {}
        if isinstance(pizza, (int, float)):
            out["pizza"] = float(pizza)
        if isinstance(nightlife, (int, float)):
            out["nightlife"] = float(nightlife)
        return out or None
    except json.JSONDecodeError:
        return None


def _serpapi_limits() -> Tuple[int, int]:
    """Return (hourly_cap, monthly_cap) for hard quota guardrails."""
    hourly = int(os.getenv("PENTAGON_SIGNALS_SERPAPI_HOURLY_CAP", "50") or "50")
    monthly = int(os.getenv("PENTAGON_SIGNALS_SERPAPI_MONTHLY_CAP", "250") or "250")
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
    """Atomically try to reserve `needed` SerpAPI searches from local counters."""
    now = datetime.now(timezone.utc)
    hour_bucket = _hour_bucket_utc(now)
    month_bucket = _month_bucket_utc(now)
    hourly_cap, monthly_cap = _serpapi_limits()

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


async def _run_async_core(conflict: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    fetched_at = utc_now_iso()
    sources: List[SourceResult] = []

    if not _env_true("PENTAGON_SIGNALS_ENABLED", default=True):
        summary = "PENTAGON_SIGNALS: disabled via PENTAGON_SIGNALS_ENABLED."
        duration_ms = int((time.perf_counter() - t0) * 1000)
        meta = build_agent_meta(
            "pentagon",
            fetched_at,
            duration_ms,
            sources,
            has_any_data=False,
            fallback_used=False,
            error_summary="disabled",
            data_confidence="degraded",
        )
        return {
            "pentagon_score": 0.0,
            "venues": [],
            "summary": summary,
            "data_confidence": "degraded",
            "_meta": meta,
        }

    manual = _manual_scores()
    api_key = (os.getenv("SERPAPI_KEY") or "").strip()
    venues_cfg = _load_venues()

    venue_rows: List[Dict[str, Any]] = []
    scores: List[float] = []

    if manual:
        for v in venues_cfg:
            role = v.get("role") or ""
            m = manual.get(str(role))
            if isinstance(m, (int, float)):
                sc = max(0.0, min(100.0, float(m)))
                scores.append(sc)
                venue_rows.append(
                    {
                        "role": role,
                        "label": v.get("label", ""),
                        "score": sc,
                        "source": "manual",
                        "note": "PENTAGON_SIGNALS_MANUAL_SCORES",
                    }
                )
        sources.append(
            SourceResult(
                name="pentagon_signals_manual",
                status="ok",
                reference_urls=[],
            )
        )
    elif not api_key:
        summary = (
            "PENTAGON_SIGNALS: no SERPAPI_KEY (and no PENTAGON_SIGNALS_MANUAL_SCORES). "
            "Informal Pentagon-area pizza/nightlife proxy not available."
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        meta = build_agent_meta(
            "pentagon",
            fetched_at,
            duration_ms,
            sources,
            has_any_data=False,
            fallback_used=True,
            error_summary="missing SERPAPI_KEY",
            data_confidence="degraded",
        )
        return {
            "pentagon_score": 0.0,
            "venues": [],
            "summary": summary,
            "data_confidence": "degraded",
            "_meta": meta,
        }
    else:
        needed_searches = len(venues_cfg)
        allowed, quota = _quota_try_consume(needed_searches)
        if not allowed:
            summary = (
                "PENTAGON_SIGNALS: SerpAPI hard cap reached. "
                f"Need {needed_searches} search(es), but quota state is "
                f"{quota.get('hour_count', 0)}/{quota.get('hourly_cap', 0)} this UTC hour and "
                f"{quota.get('month_count', 0)}/{quota.get('monthly_cap', 0)} this UTC month."
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            meta = build_agent_meta(
                "pentagon",
                fetched_at,
                duration_ms,
                sources,
                has_any_data=False,
                fallback_used=True,
                error_summary="serpapi_quota_capped",
                data_confidence="degraded",
            )
            return {
                "pentagon_score": 0.0,
                "venues": [],
                "summary": summary,
                "data_confidence": "degraded",
                "disclaimer": "Hard quota guard blocked live SerpAPI call to protect rate limits.",
                "_meta": meta,
                "quota": quota,
            }
        for v in venues_cfg:
            q = v.get("query") or ""
            label = v.get("label") or q
            role = v.get("role") or "venue"
            try:
                payload = await _serpapi_google_maps(q, api_key)
                err = payload.get("error")
                if err:
                    venue_rows.append(
                        {
                            "role": role,
                            "label": label,
                            "score": 0.0,
                            "source": "serpapi",
                            "error": str(err)[:200],
                        }
                    )
                    sources.append(
                        SourceResult(
                            name=f"serpapi:{role}",
                            status="error",
                            reference_urls=[],
                        )
                    )
                    continue
                blocks = _pick_place_blocks(payload)
                best_sc = 0.0
                best_note = ""
                place_title = ""
                for b in blocks[:8]:
                    sc, note = _extract_busy_from_place(b)
                    if sc > best_sc:
                        best_sc = sc
                        best_note = note
                        place_title = str(b.get("title") or b.get("name") or "")[:120]
                if best_sc > 0:
                    scores.append(best_sc)
                venue_rows.append(
                    {
                        "role": role,
                        "label": label,
                        "query": q[:200],
                        "matched_title": place_title,
                        "score": round(best_sc, 1),
                        "detail": best_note,
                        "source": "serpapi_google_maps",
                    }
                )
                sources.append(
                    SourceResult(
                        name=f"serpapi:{role}",
                        status="ok" if best_sc > 0 else "degraded",
                        reference_urls=[],
                    )
                )
            except Exception as e:
                logger.warning("pentagon_signals venue fetch failed (%s): %s", role, e)
                venue_rows.append(
                    {
                        "role": role,
                        "label": label,
                        "score": 0.0,
                        "error": str(e)[:200],
                    }
                )
                sources.append(
                    SourceResult(
                        name=f"serpapi:{role}",
                        status="error",
                        reference_urls=[],
                    )
                )

    if scores:
        combined = sum(scores) / len(scores)
    else:
        combined = 0.0

    # Informal signal: dampen so it cannot dominate real intel
    display_score = round(min(75.0, combined * 0.85), 1)

    parts = [
        "PENTAGON_SIGNALS (informal / anecdotal; not verified intelligence):",
        f"blended proxy {display_score:.0f}/100 from {len(venues_cfg)} venue(s).",
    ]
    if venue_rows:
        for vr in venue_rows:
            if vr.get("score"):
                parts.append(
                    f" — {vr.get('label', '?')}: {float(vr.get('score') or 0):.0f}"
                    + (f" ({vr.get('detail')})" if vr.get("detail") else "")
                )
    summary = " ".join(parts)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    meta = build_agent_meta(
        "pentagon",
        fetched_at,
        duration_ms,
        sources,
        has_any_data=bool(scores),
        fallback_used=not bool(scores) and bool(api_key or manual),
        error_summary=None if scores else "no_busy_signal",
        data_confidence="estimated" if scores else "degraded",
    )

    return {
        "pentagon_score": display_score,
        "venues": venue_rows,
        "summary": summary,
        "data_confidence": "estimated" if scores else "degraded",
        "disclaimer": "Anecdotal DC-area venue busyness proxy; corroborate with primary sources.",
        "_meta": meta,
    }


def run_pentagon_signals_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Entry point: SerpAPI Google Maps popular-times / live busyness for configured venues."""
    _ = conflict
    _ = peers
    try:
        return run_async(_run_async_core(conflict))
    except Exception as e:
        logger.exception("PENTAGON_SIGNALS agent error: %s", e)
        fb = get_agent_fallback("pentagon")
        fb["summary"] = f"PENTAGON_SIGNALS error: {e}"
        fb["data_confidence"] = "degraded"
        return fb
