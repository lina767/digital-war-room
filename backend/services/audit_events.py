from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from services.pg_sync import effective_postgres_url
from services.privacy_sanitize import pseudonymize

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_audit_event(
    *,
    event_type: str,
    actor_type: str = "system",
    actor_id: str | None = None,
    tenant_id: str | None = None,
    object_type: str,
    object_id: str | None = None,
    outcome: str = "success",
    reason_code: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    event = {
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id_pseudonymized": pseudonymize(actor_id),
        "tenant_id": tenant_id,
        "object_type": object_type,
        "object_id_hash": pseudonymize(object_id),
        "outcome": outcome,
        "reason_code": reason_code,
        "timestamp": _utc_now_iso(),
        "meta": meta or {},
    }
    logger.info("audit_event %s", json.dumps(event, ensure_ascii=True, sort_keys=True))

    db_url = effective_postgres_url()
    if not db_url:
        return
    try:
        import asyncpg
    except Exception:
        return
    try:
        conn = await asyncpg.connect(db_url, timeout=10.0)
    except Exception as e:
        logger.warning("audit_event connect failed: %s", e)
        return
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_audit_events (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id_pseudonymized TEXT,
                tenant_id UUID NULL,
                object_type TEXT NOT NULL,
                object_id_hash TEXT,
                outcome TEXT NOT NULL,
                reason_code TEXT,
                event_json JSONB NOT NULL
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO compliance_audit_events (
                event_type, actor_type, actor_id_pseudonymized, tenant_id,
                object_type, object_id_hash, outcome, reason_code, event_json
            )
            VALUES ($1, $2, $3, NULLIF($4, '')::uuid, $5, $6, $7, $8, $9::jsonb)
            """,
            event["event_type"],
            event["actor_type"],
            event["actor_id_pseudonymized"],
            tenant_id or "",
            event["object_type"],
            event["object_id_hash"],
            event["outcome"],
            event["reason_code"],
            json.dumps(event),
        )
    except Exception as e:
        logger.warning("audit_event persist failed: %s", e)
    finally:
        await conn.close()


async def prune_compliance_audit_events(days: int) -> int:
    db_url = effective_postgres_url()
    if not db_url:
        return 0
    try:
        import asyncpg
    except Exception:
        return 0
    try:
        conn = await asyncpg.connect(db_url, timeout=10.0)
    except Exception:
        return 0
    try:
        result = await conn.execute(
            """
            DELETE FROM compliance_audit_events
            WHERE created_at < NOW() - ($1::text || ' days')::interval
            """,
            max(1, int(days)),
        )
        return int((result or "DELETE 0").split()[-1])
    except Exception:
        return 0
    finally:
        await conn.close()

