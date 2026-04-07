"""
Layer 1 raw feed snapshot persistence.

Stores immutable pre-filtered feed responses in Postgres when DATABASE_URL is
usable; otherwise falls back to local SQLite.
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
from typing import Any, Dict, List, Optional

from services.pg_sync import connection, use_postgres

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.getenv("RAW_FEED_SNAPSHOTS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "raw_feed_snapshots.sqlite")
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_conflict_key(conflict_key: Optional[str]) -> Optional[str]:
    if conflict_key is None:
        return None
    s = str(conflict_key).strip().lower()
    if not s:
        return None
    return s[:240]


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_feed_snapshots (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            source TEXT NOT NULL,
            query_params TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            conflict_key TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_feed_source_conflict_fetched
        ON raw_feed_snapshots (source, conflict_key, fetched_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_feed_tenant_conflict_fetched
        ON raw_feed_snapshots (tenant_id, conflict_key, fetched_at DESC)
        """
    )
    conn.commit()
    return conn


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: Any) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _to_json_data(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def write_feed_snapshot(
    *,
    source: str,
    raw_payload: Any,
    query_params: Optional[Dict[str, Any]] = None,
    conflict_key: Optional[str] = None,
    tenant_id: uuid.UUID | str | None = None,
    dedup_latest: bool = True,
) -> Optional[str]:
    """
    Persist one pre-filtered feed response snapshot.

    Returns snapshot id, or None on failure.
    """
    source_norm = (source or "").strip().lower()
    if not source_norm:
        return None
    if raw_payload is None:
        return None

    tid = str(tenant_id) if tenant_id else None
    conflict_norm = _normalize_conflict_key(conflict_key)
    params = query_params or {}
    payload_hash = _payload_hash(raw_payload)
    snapshot_id = str(uuid.uuid4())
    fetched_at = _utc_now_iso()

    if use_postgres():
        try:
            from psycopg.types.json import Jsonb

            with connection() as conn:
                with conn.cursor() as cur:
                    if dedup_latest:
                        cur.execute(
                            """
                            SELECT content_hash
                            FROM raw_feed_snapshots
                            WHERE source = %s
                              AND COALESCE(conflict_key, '') = COALESCE(%s, '')
                              AND COALESCE(tenant_id::text, '') = COALESCE(%s, '')
                            ORDER BY fetched_at DESC
                            LIMIT 1
                            """,
                            (source_norm, conflict_norm, tid),
                        )
                        row = cur.fetchone()
                        if row and row[0] == payload_hash:
                            return None

                    cur.execute(
                        """
                        INSERT INTO raw_feed_snapshots
                            (id, tenant_id, source, query_params, raw_payload, content_hash, conflict_key, fetched_at)
                        VALUES
                            (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::timestamptz)
                        """,
                        (
                            snapshot_id,
                            tid,
                            source_norm,
                            Jsonb(params),
                            Jsonb(raw_payload),
                            payload_hash,
                            conflict_norm,
                            fetched_at,
                        ),
                    )
                conn.commit()
            return snapshot_id
        except Exception as e:
            logger.warning("feed snapshot Postgres write failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        if dedup_latest:
            row = conn.execute(
                """
                SELECT content_hash
                FROM raw_feed_snapshots
                WHERE source = ?
                  AND COALESCE(conflict_key, '') = COALESCE(?, '')
                  AND COALESCE(tenant_id, '') = COALESCE(?, '')
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (source_norm, conflict_norm, tid),
            ).fetchone()
            if row and row[0] == payload_hash:
                return None

        conn.execute(
            """
            INSERT INTO raw_feed_snapshots
                (id, tenant_id, source, query_params, raw_payload, content_hash, conflict_key, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                tid,
                source_norm,
                _json_dumps(params),
                _json_dumps(raw_payload),
                payload_hash,
                conflict_norm,
                fetched_at,
            ),
        )
        conn.commit()
        return snapshot_id
    except Exception as e:
        logger.warning("feed snapshot SQLite write failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def read_feed_window(
    *,
    source: str,
    conflict_key: Optional[str],
    since_iso: str,
    until_iso: Optional[str] = None,
    tenant_id: uuid.UUID | str | None = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Read snapshots for a source/conflict in a time window (newest first)."""
    source_norm = (source or "").strip().lower()
    if not source_norm:
        return []
    tid = str(tenant_id) if tenant_id else None
    conflict_norm = _normalize_conflict_key(conflict_key)
    until_val = until_iso or _utc_now_iso()
    limit = max(1, min(2000, int(limit)))

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id::text, tenant_id::text, source, query_params, raw_payload,
                               content_hash, conflict_key, fetched_at
                        FROM raw_feed_snapshots
                        WHERE source = %s
                          AND COALESCE(conflict_key, '') = COALESCE(%s, '')
                          AND COALESCE(tenant_id::text, '') = COALESCE(%s, '')
                          AND fetched_at >= %s::timestamptz
                          AND fetched_at <= %s::timestamptz
                        ORDER BY fetched_at DESC
                        LIMIT %s
                        """,
                        (source_norm, conflict_norm, tid, since_iso, until_val, limit),
                    )
                    rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "id": r[0],
                        "tenant_id": r[1],
                        "source": r[2],
                        "query_params": _to_json_data(r[3]),
                        "raw_payload": _to_json_data(r[4]),
                        "content_hash": r[5],
                        "conflict_key": r[6],
                        "fetched_at": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7]),
                    }
                )
            return out
        except Exception as e:
            logger.warning("feed snapshot Postgres read failed (%s), falling back to SQLite", e)

    conn = _ensure_sqlite()
    try:
        rows = conn.execute(
            """
            SELECT id, tenant_id, source, query_params, raw_payload, content_hash, conflict_key, fetched_at
            FROM raw_feed_snapshots
            WHERE source = ?
              AND COALESCE(conflict_key, '') = COALESCE(?, '')
              AND COALESCE(tenant_id, '') = COALESCE(?, '')
              AND fetched_at >= ?
              AND fetched_at <= ?
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (source_norm, conflict_norm, tid, since_iso, until_val, limit),
        ).fetchall()
        return [
            {
                "id": r[0],
                "tenant_id": r[1],
                "source": r[2],
                "query_params": _to_json_data(r[3]),
                "raw_payload": _to_json_data(r[4]),
                "content_hash": r[5],
                "conflict_key": r[6],
                "fetched_at": r[7],
            }
            for r in rows
        ]
    finally:
        conn.close()
