"""
Persist analysis provenance snapshots to Postgres when DATABASE_URL is set.

Stores per-agent ``_meta`` (sources, processing steps, confidence) plus CEO-level
``provenance_index`` for compliance audit trails. Best-effort: failures are logged only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from services.pg_sync import effective_postgres_url

logger = logging.getLogger(__name__)

AGENT_KEYS_FOR_SNAPSHOT: List[str] = [
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
]


def build_provenance_snapshot(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract audit-relevant metadata from a full analysis result."""
    agents: Dict[str, Any] = {}
    for k in AGENT_KEYS_FOR_SNAPSHOT:
        block = result.get(k)
        if isinstance(block, dict) and isinstance(block.get("_meta"), dict):
            agents[k] = block["_meta"]
    return {
        "analysis_run_id": result.get("analysis_run_id"),
        "provenance_index": result.get("provenance_index"),
        "agents": agents,
    }


async def persist_analysis_audit(conflict: str, result: Dict[str, Any]) -> None:
    """Insert or update one row in ``analysis_audit`` for this run."""
    url = effective_postgres_url()
    if not url:
        return
    run_id = result.get("analysis_run_id")
    if not run_id or not isinstance(run_id, str):
        return
    try:
        import asyncpg
    except ImportError:
        logger.debug("asyncpg not installed; analysis audit skipped")
        return

    snap = build_provenance_snapshot(result)
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
    except Exception as e:
        logger.warning("analysis audit: DB connect failed: %s", e)
        return
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_audit (
                run_id UUID PRIMARY KEY,
                conflict TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                provenance_json JSONB NOT NULL
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO analysis_audit (run_id, conflict, provenance_json)
            VALUES ($1::uuid, $2, $3::jsonb)
            ON CONFLICT (run_id) DO UPDATE SET
                provenance_json = EXCLUDED.provenance_json,
                conflict = EXCLUDED.conflict
            """,
            run_id,
            conflict,
            json.dumps(snap),
        )
    except Exception as e:
        logger.warning("analysis audit persist failed: %s", e)
    finally:
        await conn.close()


async def fetch_analysis_audit(run_id: str) -> Optional[Dict[str, Any]]:
    """Load a stored provenance snapshot by run UUID string."""
    url = effective_postgres_url()
    if not url:
        return None
    try:
        import asyncpg
    except ImportError:
        return None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
    except Exception as e:
        logger.warning("analysis audit fetch: DB connect failed: %s", e)
        return None
    try:
        row = await conn.fetchrow(
            """
            SELECT run_id, conflict, created_at, provenance_json
            FROM analysis_audit
            WHERE run_id = $1::uuid
            """,
            run_id,
        )
        if not row:
            return None
        pj = row["provenance_json"]
        if isinstance(pj, str):
            pj = json.loads(pj)
        return {
            "run_id": str(row["run_id"]),
            "conflict": row["conflict"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "provenance": pj,
        }
    except Exception as e:
        logger.warning("analysis audit fetch failed: %s", e)
        return None
    finally:
        await conn.close()


async def prune_analysis_audit(days: int) -> int:
    """Delete old analysis_audit rows older than N days."""
    url = effective_postgres_url()
    if not url:
        return 0
    try:
        import asyncpg
    except ImportError:
        return 0
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
    except Exception:
        return 0
    try:
        result = await conn.execute(
            """
            DELETE FROM analysis_audit
            WHERE created_at < NOW() - ($1::text || ' days')::interval
            """,
            max(1, int(days)),
        )
        return int((result or "DELETE 0").split()[-1])
    except Exception as e:
        logger.warning("analysis audit prune failed: %s", e)
        return 0
    finally:
        await conn.close()
