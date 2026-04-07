"""
Persistent store for chat feedback events.

Writes to Postgres when DATABASE_URL is configured; otherwise keeps a bounded
in-memory fallback so feedback is never dropped hard.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MEMORY_MAX = int(os.getenv("CHAT_FEEDBACK_MEMORY_MAX", "500"))
_memory_feedback: deque = deque(maxlen=max(50, _MEMORY_MAX))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def persist_chat_feedback(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist one chat feedback event.
    Returns storage details, never raises.
    """
    safe_event = dict(event)
    safe_event.setdefault("created_at", _now_iso())
    safe_event["sources"] = list(safe_event.get("sources") or [])

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        _memory_feedback.append(safe_event)
        return {"stored": True, "storage": "memory"}

    try:
        import asyncpg
    except ImportError:
        _memory_feedback.append(safe_event)
        return {"stored": True, "storage": "memory"}

    conn = None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_feedback (
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                tenant_id UUID NULL,
                response_id UUID NULL,
                conflict TEXT NOT NULL,
                question_type TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                confidence_score DOUBLE PRECISION NOT NULL,
                sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                helpful BOOLEAN NOT NULL,
                comment TEXT NULL
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO chat_feedback (
                id,
                tenant_id,
                response_id,
                conflict,
                question_type,
                question,
                answer,
                confidence_score,
                sources_json,
                helpful,
                comment
            ) VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)
            """,
            str(uuid.uuid4()),
            safe_event.get("tenant_id"),
            safe_event.get("response_id"),
            safe_event.get("conflict", "Unknown"),
            safe_event.get("question_type", "source_check"),
            safe_event.get("question", ""),
            safe_event.get("answer", ""),
            float(safe_event.get("confidence_score") or 0.0),
            json.dumps(safe_event.get("sources") or []),
            bool(safe_event.get("helpful")),
            (safe_event.get("comment") or None),
        )
        return {"stored": True, "storage": "database"}
    except Exception as e:
        logger.warning("chat feedback persist failed, falling back to memory: %s", e)
        _memory_feedback.append(safe_event)
        return {"stored": True, "storage": "memory"}
    finally:
        if conn is not None:
            await conn.close()


def get_memory_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    """Debug helper to inspect fallback memory store."""
    n = max(1, min(int(limit), len(_memory_feedback)))
    return list(_memory_feedback)[-n:]


def _summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    helpful_total = sum(1 for r in rows if bool(r.get("helpful")))
    by_type: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        qt = str(row.get("question_type") or "unknown")
        bucket = by_type.setdefault(
            qt,
            {
                "question_type": qt,
                "count": 0,
                "helpful_count": 0,
                "helpful_rate": 0.0,
                "avg_confidence": 0.0,
            },
        )
        bucket["count"] += 1
        if bool(row.get("helpful")):
            bucket["helpful_count"] += 1
        try:
            bucket["avg_confidence"] += float(row.get("confidence_score") or 0.0)
        except Exception:
            pass
    for bucket in by_type.values():
        c = max(1, int(bucket["count"]))
        bucket["helpful_rate"] = round(float(bucket["helpful_count"]) / c, 3)
        bucket["avg_confidence"] = round(float(bucket["avg_confidence"]) / c, 3)
    return {
        "total_feedback": total,
        "helpful_total": helpful_total,
        "helpful_rate": round(float(helpful_total) / max(1, total), 3),
        "by_question_type": sorted(by_type.values(), key=lambda x: x["count"], reverse=True),
    }


async def get_chat_feedback_summary(
    *,
    tenant_id: Optional[str],
    days: int = 7,
    limit: int = 500,
) -> Dict[str, Any]:
    """Return helpful-rate summary, grouped by question_type."""
    safe_days = max(1, min(int(days), 90))
    safe_limit = max(10, min(int(limit), 2000))
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        rows = list(_memory_feedback)[-safe_limit:]
        if tenant_id:
            rows = [r for r in rows if str(r.get("tenant_id") or "") == str(tenant_id)]
        return {"storage": "memory", **_summarize_rows(rows)}

    try:
        import asyncpg
    except ImportError:
        rows = list(_memory_feedback)[-safe_limit:]
        if tenant_id:
            rows = [r for r in rows if str(r.get("tenant_id") or "") == str(tenant_id)]
        return {"storage": "memory", **_summarize_rows(rows)}

    conn = None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
        records = await conn.fetch(
            """
            SELECT question_type, confidence_score, helpful
            FROM chat_feedback
            WHERE created_at >= NOW() - ($1::text || ' days')::interval
              AND ($2::uuid IS NULL OR tenant_id = $2::uuid)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            safe_days,
            tenant_id,
            safe_limit,
        )
        rows = [
            {
                "question_type": r["question_type"],
                "confidence_score": r["confidence_score"],
                "helpful": r["helpful"],
            }
            for r in records
        ]
        return {"storage": "database", **_summarize_rows(rows)}
    except Exception as e:
        logger.warning("chat feedback summary failed, using memory fallback: %s", e)
        rows = list(_memory_feedback)[-safe_limit:]
        if tenant_id:
            rows = [r for r in rows if str(r.get("tenant_id") or "") == str(tenant_id)]
        return {"storage": "memory", **_summarize_rows(rows)}
    finally:
        if conn is not None:
            await conn.close()
