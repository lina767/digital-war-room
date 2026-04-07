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
_memory_responses: deque = deque(maxlen=max(50, _MEMORY_MAX))


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
    by_day: Dict[str, Dict[str, Any]] = {}
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
        created_at = str(row.get("created_at") or "")
        day = created_at[:10] if len(created_at) >= 10 else "unknown"
        day_bucket = by_day.setdefault(
            day,
            {
                "day": day,
                "count": 0,
                "helpful_count": 0,
                "helpful_rate": 0.0,
            },
        )
        day_bucket["count"] += 1
        if bool(row.get("helpful")):
            day_bucket["helpful_count"] += 1
    for bucket in by_type.values():
        c = max(1, int(bucket["count"]))
        bucket["helpful_rate"] = round(float(bucket["helpful_count"]) / c, 3)
        bucket["avg_confidence"] = round(float(bucket["avg_confidence"]) / c, 3)
    for day_bucket in by_day.values():
        c = max(1, int(day_bucket["count"]))
        day_bucket["helpful_rate"] = round(float(day_bucket["helpful_count"]) / c, 3)
    return {
        "total_feedback": total,
        "helpful_total": helpful_total,
        "helpful_rate": round(float(helpful_total) / max(1, total), 3),
        "by_question_type": sorted(by_type.values(), key=lambda x: x["count"], reverse=True),
        "trend_days": sorted(by_day.values(), key=lambda x: x["day"]),
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
            SELECT question_type, confidence_score, helpful, created_at
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
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
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


async def persist_chat_response(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist one chat answer keyed by response_id for authoritative feedback linkage.
    Returns storage details, never raises.
    """
    safe_event = dict(event)
    safe_event.setdefault("created_at", _now_iso())
    safe_event["sources"] = list(safe_event.get("sources") or [])
    _memory_responses.append(safe_event)

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return {"stored": True, "storage": "memory"}

    try:
        import asyncpg
    except ImportError:
        return {"stored": True, "storage": "memory"}

    conn = None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
        await conn.execute(
            """
            INSERT INTO chat_responses (
                response_id,
                tenant_id,
                conflict,
                question_type,
                question,
                answer,
                confidence_score,
                sources_json,
                fallback_used
            ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9)
            ON CONFLICT (response_id) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                conflict = EXCLUDED.conflict,
                question_type = EXCLUDED.question_type,
                question = EXCLUDED.question,
                answer = EXCLUDED.answer,
                confidence_score = EXCLUDED.confidence_score,
                sources_json = EXCLUDED.sources_json,
                fallback_used = EXCLUDED.fallback_used
            """,
            safe_event.get("response_id"),
            safe_event.get("tenant_id"),
            safe_event.get("conflict", "Unknown"),
            safe_event.get("question_type", "situation_overview"),
            safe_event.get("question", ""),
            safe_event.get("answer", ""),
            float(safe_event.get("confidence_score") or 0.0),
            json.dumps(safe_event.get("sources") or []),
            bool(safe_event.get("fallback_used")),
        )
        return {"stored": True, "storage": "database"}
    except Exception as e:
        logger.warning("chat response persist failed, using memory fallback: %s", e)
        return {"stored": True, "storage": "memory"}
    finally:
        if conn is not None:
            await conn.close()


async def resolve_chat_response(*, response_id: str, tenant_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Resolve a previously persisted chat response by ID and tenant.
    """
    rid = str(response_id or "").strip()
    if not rid:
        return None

    for row in reversed(_memory_responses):
        if str(row.get("response_id") or "") != rid:
            continue
        if tenant_id and str(row.get("tenant_id") or "") not in ("", str(tenant_id)):
            continue
        return {
            "response_id": rid,
            "conflict": row.get("conflict"),
            "question_type": row.get("question_type"),
            "question": row.get("question"),
            "answer": row.get("answer"),
            "confidence_score": row.get("confidence_score"),
            "sources": list(row.get("sources") or []),
            "fallback_used": bool(row.get("fallback_used")),
        }

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None

    try:
        import asyncpg
    except ImportError:
        return None

    conn = None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
        row = await conn.fetchrow(
            """
            SELECT
                response_id,
                tenant_id,
                conflict,
                question_type,
                question,
                answer,
                confidence_score,
                sources_json,
                fallback_used
            FROM chat_responses
            WHERE response_id = $1::uuid
              AND ($2::uuid IS NULL OR tenant_id = $2::uuid)
            LIMIT 1
            """,
            rid,
            tenant_id,
        )
        if not row:
            return None
        return {
            "response_id": str(row["response_id"]),
            "conflict": row["conflict"],
            "question_type": row["question_type"],
            "question": row["question"],
            "answer": row["answer"],
            "confidence_score": float(row["confidence_score"] or 0.0),
            "sources": list(row["sources_json"] or []),
            "fallback_used": bool(row["fallback_used"]),
        }
    except Exception as e:
        logger.warning("chat response resolve failed: %s", e)
        return None
    finally:
        if conn is not None:
            await conn.close()
