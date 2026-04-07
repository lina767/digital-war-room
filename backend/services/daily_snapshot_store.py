"""
Layer 5 daily materialized world-state snapshots.

Postgres primary (with tenant-scoped RLS), SQLite fallback for local/dev.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.pg_sync import connection, use_postgres
from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.getenv("DAILY_WORLD_SNAPSHOTS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "daily_world_snapshots.sqlite")
)


def _normalize_conflict_key(conflict: str) -> str:
    s = (conflict or "").strip().lower()
    return s[:240] if s else "unknown"


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_world_snapshots (
            id TEXT PRIMARY KEY,
            conflict_key TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            top_signals_json TEXT NOT NULL,
            chokepoint_status_json TEXT NOT NULL,
            agent_scores_json TEXT NOT NULL,
            active_entities_json TEXT NOT NULL,
            diff_vs_prior_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (conflict_key, tenant_id, snapshot_date)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_world_snapshots_lookup
        ON daily_world_snapshots (tenant_id, conflict_key, snapshot_date DESC)
        """
    )
    conn.commit()
    return conn


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True, separators=(",", ":"))


def _to_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def upsert_daily_snapshot(
    *,
    conflict: str,
    snapshot_date: date,
    payload: Dict[str, Any],
    tenant_id: uuid.UUID | str | None = None,
) -> Optional[str]:
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    row_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    top_signals = payload.get("top_signals") or []
    chokepoint_status = payload.get("chokepoint_status") or []
    agent_scores = payload.get("agent_scores") or {}
    active_entities = payload.get("active_entities") or []
    diff_vs_prior = payload.get("diff_vs_prior") or {}

    if use_postgres():
        try:
            from psycopg.types.json import Jsonb

            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        INSERT INTO daily_world_snapshots
                            (id, conflict_key, tenant_id, snapshot_date, top_signals, chokepoint_status,
                             agent_scores, active_entities, diff_vs_prior, created_at)
                        VALUES
                            (%s::uuid, %s, %s::uuid, %s::date, %s::jsonb, %s::jsonb,
                             %s::jsonb, %s::jsonb, %s::jsonb, %s::timestamptz)
                        ON CONFLICT (conflict_key, tenant_id, snapshot_date)
                        DO UPDATE SET
                            top_signals = EXCLUDED.top_signals,
                            chokepoint_status = EXCLUDED.chokepoint_status,
                            agent_scores = EXCLUDED.agent_scores,
                            active_entities = EXCLUDED.active_entities,
                            diff_vs_prior = EXCLUDED.diff_vs_prior,
                            created_at = EXCLUDED.created_at
                        RETURNING id::text
                        """,
                        (
                            row_id,
                            conflict_key,
                            tid,
                            snapshot_date.isoformat(),
                            Jsonb(top_signals),
                            Jsonb(chokepoint_status),
                            Jsonb(agent_scores),
                            Jsonb(active_entities),
                            Jsonb(diff_vs_prior),
                            created_at,
                        ),
                    )
                    saved = cur.fetchone()
                conn.commit()
            return str(saved[0]) if saved and saved[0] else row_id
        except Exception as e:
            logger.warning("daily_snapshot_store postgres upsert failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        existing = conn.execute(
            """
            SELECT id FROM daily_world_snapshots
            WHERE conflict_key = ? AND tenant_id = ? AND snapshot_date = ?
            """,
            (conflict_key, tid, snapshot_date.isoformat()),
        ).fetchone()
        use_id = str(existing[0]) if existing and existing[0] else row_id
        conn.execute(
            """
            INSERT INTO daily_world_snapshots
                (id, conflict_key, tenant_id, snapshot_date, top_signals_json, chokepoint_status_json,
                 agent_scores_json, active_entities_json, diff_vs_prior_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conflict_key, tenant_id, snapshot_date) DO UPDATE SET
                top_signals_json = excluded.top_signals_json,
                chokepoint_status_json = excluded.chokepoint_status_json,
                agent_scores_json = excluded.agent_scores_json,
                active_entities_json = excluded.active_entities_json,
                diff_vs_prior_json = excluded.diff_vs_prior_json,
                created_at = excluded.created_at
            """,
            (
                use_id,
                conflict_key,
                tid,
                snapshot_date.isoformat(),
                _json_dumps(top_signals),
                _json_dumps(chokepoint_status),
                _json_dumps(agent_scores),
                _json_dumps(active_entities),
                _json_dumps(diff_vs_prior),
                created_at,
            ),
        )
        conn.commit()
        return use_id
    except Exception as e:
        logger.warning("daily_snapshot_store sqlite upsert failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def get_latest_daily_snapshot(
    *,
    conflict: str,
    tenant_id: uuid.UUID | str | None = None,
) -> Optional[Dict[str, Any]]:
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        SELECT id::text, conflict_key, tenant_id::text, snapshot_date::text,
                               top_signals, chokepoint_status, agent_scores, active_entities,
                               diff_vs_prior, created_at
                        FROM daily_world_snapshots
                        WHERE conflict_key = %s AND tenant_id = %s::uuid
                        ORDER BY snapshot_date DESC
                        LIMIT 1
                        """,
                        (conflict_key, tid),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "conflict_key": row[1],
                "tenant_id": row[2],
                "snapshot_date": row[3],
                "top_signals": _to_json(row[4]),
                "chokepoint_status": _to_json(row[5]),
                "agent_scores": _to_json(row[6]),
                "active_entities": _to_json(row[7]),
                "diff_vs_prior": _to_json(row[8]),
                "created_at": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
            }
        except Exception as e:
            logger.warning("daily_snapshot_store postgres latest failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        row = conn.execute(
            """
            SELECT id, conflict_key, tenant_id, snapshot_date, top_signals_json, chokepoint_status_json,
                   agent_scores_json, active_entities_json, diff_vs_prior_json, created_at
            FROM daily_world_snapshots
            WHERE conflict_key = ? AND tenant_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (conflict_key, tid),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "conflict_key": row[1],
            "tenant_id": row[2],
            "snapshot_date": row[3],
            "top_signals": _to_json(row[4]),
            "chokepoint_status": _to_json(row[5]),
            "agent_scores": _to_json(row[6]),
            "active_entities": _to_json(row[7]),
            "diff_vs_prior": _to_json(row[8]),
            "created_at": row[9],
        }
    finally:
        conn.close()


def list_daily_snapshots(
    *,
    conflict: str,
    tenant_id: uuid.UUID | str | None = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    conflict_key = _normalize_conflict_key(conflict)
    limit = max(1, min(365, int(limit)))

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tid,))
                    cur.execute(
                        """
                        SELECT id::text, snapshot_date::text, created_at, agent_scores
                        FROM daily_world_snapshots
                        WHERE conflict_key = %s AND tenant_id = %s::uuid
                        ORDER BY snapshot_date DESC
                        LIMIT %s
                        """,
                        (conflict_key, tid, limit),
                    )
                    rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "snapshot_date": r[1],
                    "created_at": r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2]),
                    "agent_scores": _to_json(r[3]),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("daily_snapshot_store postgres list failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        rows = conn.execute(
            """
            SELECT id, snapshot_date, created_at, agent_scores_json
            FROM daily_world_snapshots
            WHERE conflict_key = ? AND tenant_id = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
            """,
            (conflict_key, tid, limit),
        ).fetchall()
        return [
            {"id": r[0], "snapshot_date": r[1], "created_at": r[2], "agent_scores": _to_json(r[3])} for r in rows
        ]
    finally:
        conn.close()
