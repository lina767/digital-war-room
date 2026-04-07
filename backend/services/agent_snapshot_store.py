"""
Layer 3 agent snapshot persistence.

Stores per-agent versioned outputs and computes a content-hash based changed flag.
Uses Postgres when DATABASE_URL is usable; otherwise falls back to SQLite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agents.registry import DEFAULT_AGENTS
from services.pg_sync import connection, use_postgres
from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("AGENT_SNAPSHOTS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "agent_snapshots.sqlite"))
AGENT_NAMES = tuple(d.name for d in DEFAULT_AGENTS)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_conflict_key(conflict: str) -> str:
    s = (conflict or "").strip().lower()
    return (s[:240] if s else "unknown")


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True, separators=(",", ":"))


def _content_hash(output: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(output).encode("utf-8")).hexdigest()


def _to_json_data(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_snapshots (
            id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            entity_id TEXT,
            run_id TEXT NOT NULL,
            conflict_key TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            output_json TEXT NOT NULL,
            confidence REAL,
            sources_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            changed INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_snapshots_lookup
        ON agent_snapshots (tenant_id, agent_name, conflict_key, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_snapshots_entity
        ON agent_snapshots (entity_id, created_at DESC)
        """
    )
    conn.commit()
    return conn


def _extract_confidence(block: dict[str, Any]) -> Optional[float]:
    for key in ("dq_confidence", "confidence", "confidence_score"):
        val = block.get(key)
        try:
            if val is not None:
                return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _extract_sources(block: dict[str, Any]) -> list[str]:
    out: list[str] = []
    meta = block.get("_meta")
    if isinstance(meta, dict):
        src = meta.get("sources")
        if isinstance(src, list):
            for s in src:
                if isinstance(s, str) and s.strip():
                    out.append(s.strip()[:240])
    return out


def save_agent_snapshot(
    *,
    agent_name: str,
    run_id: str,
    conflict: str,
    output_block: dict[str, Any],
    tenant_id: uuid.UUID | str | None = None,
    entity_id: uuid.UUID | str | None = None,
    created_at: Optional[str] = None,
) -> Optional[str]:
    if not agent_name or not isinstance(output_block, dict):
        return None
    if not run_id:
        return None
    try:
        uuid.UUID(str(run_id))
    except Exception:
        return None

    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    out_hash = _content_hash(output_block)
    ts = created_at or _utc_now_iso()
    snap_id = str(uuid.uuid4())
    entity_id_str = str(entity_id) if entity_id else None
    confidence = _extract_confidence(output_block)
    sources = _extract_sources(output_block)
    previous_hash: Optional[str] = None

    if use_postgres():
        try:
            from psycopg.types.json import Jsonb

            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        SELECT content_hash
                        FROM agent_snapshots
                        WHERE tenant_id = %s::uuid
                          AND agent_name = %s
                          AND conflict_key = %s
                          AND COALESCE(entity_id::text, '') = COALESCE(%s, '')
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (tid, agent_name, conflict_key, entity_id_str),
                    )
                    row = cur.fetchone()
                    if row:
                        previous_hash = str(row[0])

                    cur.execute(
                        """
                        INSERT INTO agent_snapshots
                            (id, agent_name, entity_id, run_id, conflict_key, tenant_id, created_at,
                             output, confidence, sources, content_hash, changed)
                        VALUES
                            (%s::uuid, %s, %s::uuid, %s::uuid, %s, %s::uuid, %s::timestamptz,
                             %s::jsonb, %s, %s::text[], %s, %s)
                        """,
                        (
                            snap_id,
                            agent_name,
                            entity_id_str,
                            run_id,
                            conflict_key,
                            tid,
                            ts,
                            Jsonb(output_block),
                            confidence,
                            sources,
                            out_hash,
                            previous_hash != out_hash,
                        ),
                    )
                conn.commit()
            return snap_id
        except Exception as e:
            logger.warning("agent_snapshot_store postgres save failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        row = conn.execute(
            """
            SELECT content_hash
            FROM agent_snapshots
            WHERE tenant_id = ?
              AND agent_name = ?
              AND conflict_key = ?
              AND COALESCE(entity_id, '') = COALESCE(?, '')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tid, agent_name, conflict_key, entity_id_str),
        ).fetchone()
        if row:
            previous_hash = str(row[0])

        conn.execute(
            """
            INSERT INTO agent_snapshots
                (id, agent_name, entity_id, run_id, conflict_key, tenant_id, created_at,
                 output_json, confidence, sources_json, content_hash, changed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap_id,
                agent_name,
                entity_id_str,
                run_id,
                conflict_key,
                tid,
                ts,
                _json_dumps(output_block),
                confidence,
                _json_dumps(sources),
                out_hash,
                1 if previous_hash != out_hash else 0,
            ),
        )
        conn.commit()
        return snap_id
    except Exception as e:
        logger.warning("agent_snapshot_store sqlite save failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def persist_agent_snapshots_for_result(
    *,
    conflict: str,
    result: dict[str, Any],
    tenant_id: uuid.UUID | str | None = None,
) -> int:
    """
    Persist snapshots for all known top-level agent blocks in one analysis result.
    Returns count of successfully persisted snapshots.
    """
    run_id = str(result.get("analysis_run_id") or "")
    if not run_id:
        return 0
    created_at = _utc_now_iso()
    count = 0
    for agent_name in AGENT_NAMES:
        block = result.get(agent_name)
        if not isinstance(block, dict):
            continue
        # Layer 2 provides per-ship entity_id on SIGINT ships; Layer 3 starts with conflict-level snapshot.
        sid = save_agent_snapshot(
            agent_name=agent_name,
            run_id=run_id,
            conflict=conflict,
            output_block=block,
            tenant_id=tenant_id,
            entity_id=None,
            created_at=created_at,
        )
        if sid:
            count += 1
    return count


def list_recent_run_ids(
    *,
    conflict: str,
    tenant_id: uuid.UUID | str | None = None,
    limit: int = 20,
) -> list[str]:
    """List recent distinct run_ids for a conflict (newest first)."""
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    limit = max(1, min(200, int(limit)))

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        SELECT run_id::text
                        FROM (
                            SELECT run_id, MAX(created_at) AS latest_at
                            FROM agent_snapshots
                            WHERE tenant_id = %s::uuid AND conflict_key = %s
                            GROUP BY run_id
                        ) t
                        ORDER BY latest_at DESC
                        LIMIT %s
                        """,
                        (tid, conflict_key, limit),
                    )
                    rows = cur.fetchall()
            return [str(r[0]) for r in rows if r and r[0]]
        except Exception as e:
            logger.warning("agent_snapshot_store postgres list_recent_run_ids failed: %s", e)

    conn = _ensure_sqlite()
    try:
        rows = conn.execute(
            """
            SELECT run_id
            FROM (
                SELECT run_id, MAX(created_at) AS latest_at
                FROM agent_snapshots
                WHERE tenant_id = ? AND conflict_key = ?
                GROUP BY run_id
            ) t
            ORDER BY latest_at DESC
            LIMIT ?
            """,
            (tid, conflict_key, limit),
        ).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]
    finally:
        conn.close()


def list_recent_runs(
    *,
    conflict: str,
    tenant_id: uuid.UUID | str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent distinct runs with lightweight metadata (newest first)."""
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    limit = max(1, min(200, int(limit)))

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        SELECT run_id::text, MAX(created_at) AS latest_at,
                               COUNT(*) AS snapshots_total,
                               SUM(CASE WHEN changed THEN 1 ELSE 0 END) AS snapshots_changed
                        FROM agent_snapshots
                        WHERE tenant_id = %s::uuid AND conflict_key = %s
                        GROUP BY run_id
                        ORDER BY latest_at DESC
                        LIMIT %s
                        """,
                        (tid, conflict_key, limit),
                    )
                    rows = cur.fetchall()
            return [
                {
                    "run_id": str(r[0]),
                    "created_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                    "snapshots_total": int(r[2] or 0),
                    "snapshots_changed": int(r[3] or 0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("agent_snapshot_store postgres list_recent_runs failed: %s", e)

    conn = _ensure_sqlite()
    try:
        rows = conn.execute(
            """
            SELECT run_id, MAX(created_at) AS latest_at,
                   COUNT(*) AS snapshots_total,
                   SUM(CASE WHEN changed = 1 THEN 1 ELSE 0 END) AS snapshots_changed
            FROM agent_snapshots
            WHERE tenant_id = ? AND conflict_key = ?
            GROUP BY run_id
            ORDER BY latest_at DESC
            LIMIT ?
            """,
            (tid, conflict_key, limit),
        ).fetchall()
        return [
            {
                "run_id": str(r[0]),
                "created_at": str(r[1]),
                "snapshots_total": int(r[2] or 0),
                "snapshots_changed": int(r[3] or 0),
            }
            for r in rows
        ]
    finally:
        conn.close()


def load_agent_blocks_for_run(
    *,
    run_id: str,
    conflict: str,
    tenant_id: uuid.UUID | str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load one output block per agent for a run.
    For now, latest row per (agent_name, entity_id) collapses to agent-level by entity_id=None.
    """
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    out: dict[str, dict[str, Any]] = {}

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT agent_name, output, content_hash, changed, created_at
                        FROM agent_snapshots
                        WHERE tenant_id = %s::uuid
                          AND conflict_key = %s
                          AND run_id = %s::uuid
                          AND entity_id IS NULL
                        ORDER BY created_at DESC
                        """,
                        (tid, conflict_key, run_id),
                    )
                    rows = cur.fetchall()
            for row in rows:
                agent_name = str(row[0])
                if agent_name in out:
                    continue
                out[agent_name] = {
                    "output": _to_json_data(row[1]),
                    "content_hash": str(row[2]),
                    "changed": bool(row[3]),
                    "created_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
                }
            return out
        except Exception as e:
            logger.warning("agent_snapshot_store postgres load_agent_blocks_for_run failed: %s", e)

    conn = _ensure_sqlite()
    try:
        rows = conn.execute(
            """
            SELECT agent_name, output_json, content_hash, changed, created_at
            FROM agent_snapshots
            WHERE tenant_id = ?
              AND conflict_key = ?
              AND run_id = ?
              AND entity_id IS NULL
            ORDER BY created_at DESC
            """,
            (tid, conflict_key, run_id),
        ).fetchall()
        for row in rows:
            agent_name = str(row[0])
            if agent_name in out:
                continue
            out[agent_name] = {
                "output": _to_json_data(row[1]),
                "content_hash": str(row[2]),
                "changed": bool(int(row[3] or 0)),
                "created_at": str(row[4]),
            }
        return out
    finally:
        conn.close()

