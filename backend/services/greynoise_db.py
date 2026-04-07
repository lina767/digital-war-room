"""
GreyNoise snapshot persistence: PostgreSQL when DATABASE_URL is set, else SQLite file.

REST and agents read snapshots from here (no live GreyNoise in the request path).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.pg_sync import connection, use_postgres

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.getenv("GREYNOISE_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "greynoise_snapshots.db")
)


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            greynoise_score REAL NOT NULL DEFAULT 0,
            absolute_score REAL NOT NULL DEFAULT 0,
            total_events INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gn_conflict_ts
        ON greynoise_snapshots (conflict, timestamp DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict TEXT NOT NULL,
            direction TEXT NOT NULL,
            ip TEXT NOT NULL,
            classification TEXT,
            tags_json TEXT,
            metadata_json TEXT,
            snapshot_timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gn_ips_conflict_ts
        ON greynoise_ips (conflict, snapshot_timestamp DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_pending_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL,
            conflict TEXT NOT NULL,
            matched_category TEXT,
            discovered_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.commit()
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_data(obj: Any) -> Any:
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        return json.loads(obj)
    return obj


def save_snapshot(result: Any) -> None:
    total_events = int(result.outbound_count) + int(result.inbound_count)
    payload = json.dumps(result.model_dump(mode="json"))
    if use_postgres():
        try:
            from psycopg.types.json import Jsonb

            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO greynoise_snapshots
                            (conflict, snapshot_at, greynoise_score, absolute_score, total_events, data_json)
                        VALUES (%s, %s::timestamptz, %s, %s, %s, %s)
                        """,
                        (
                            result.conflict,
                            result.fetched_at,
                            result.greynoise_score,
                            result.absolute_score,
                            total_events,
                            Jsonb(result.model_dump(mode="json")),
                        ),
                    )
                conn.commit()
            return
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres save_snapshot failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        conn.execute(
            "INSERT INTO greynoise_snapshots (conflict, timestamp, greynoise_score, absolute_score, total_events, data_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.conflict,
                result.fetched_at,
                result.greynoise_score,
                result.absolute_score,
                total_events,
                payload,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_snapshot(conflict: str) -> Optional[Dict[str, Any]]:
    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT data_json FROM greynoise_snapshots
                        WHERE LOWER(conflict) = LOWER(%s) ORDER BY snapshot_at DESC LIMIT 1
                        """,
                        (conflict,),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            data = row[0]
            return _json_data(data) if data is not None else None
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres get_latest_snapshot failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        row = conn.execute(
            "SELECT data_json FROM greynoise_snapshots WHERE LOWER(conflict) = LOWER(?) ORDER BY timestamp DESC LIMIT 1",
            (conflict,),
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def _ts_out(row_ts: Any) -> str:
    if isinstance(row_ts, datetime):
        return row_ts.isoformat()
    return str(row_ts)


def get_trend_data(conflict: str, days: int = 7) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT snapshot_at, greynoise_score, absolute_score, total_events
                        FROM greynoise_snapshots
                        WHERE LOWER(conflict) = LOWER(%s) AND snapshot_at >= %s
                        ORDER BY snapshot_at ASC
                        """,
                        (conflict, cutoff),
                    )
                    rows = cur.fetchall()
            return [
                {
                    "timestamp": _ts_out(r[0]),
                    "greynoise_score": r[1],
                    "absolute_score": r[2],
                    "total_events": r[3],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres get_trend_data failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        cutoff_s = cutoff.isoformat()
        rows = conn.execute(
            "SELECT timestamp, greynoise_score, absolute_score, total_events FROM greynoise_snapshots WHERE LOWER(conflict) = LOWER(?) AND timestamp >= ? ORDER BY timestamp ASC",
            (conflict, cutoff_s),
        ).fetchall()
        return [
            {"timestamp": r[0], "greynoise_score": r[1], "absolute_score": r[2], "total_events": r[3]} for r in rows
        ]
    finally:
        conn.close()


def _get_historical_avg(conflict: str, days: int = 7) -> Optional[float]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT AVG(total_events) FROM greynoise_snapshots
                        WHERE LOWER(conflict) = LOWER(%s) AND snapshot_at >= %s
                        """,
                        (conflict, cutoff),
                    )
                    row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
            return None
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres historical avg failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        cutoff_s = cutoff.isoformat()
        row = conn.execute(
            "SELECT AVG(total_events) FROM greynoise_snapshots WHERE LOWER(conflict) = LOWER(?) AND timestamp >= ?",
            (conflict, cutoff_s),
        ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None
    finally:
        conn.close()


def _save_gnql_ips(conflict: str, direction: str, ip_records: List[Dict[str, Any]], snapshot_timestamp: str) -> None:
    if not ip_records:
        return
    now = _utc_now_iso()
    if use_postgres():
        try:
            from psycopg.types.json import Jsonb

            with connection() as conn:
                with conn.cursor() as cur:
                    for rec in ip_records[:50]:
                        ip = rec.get("ip") or rec.get("address")
                        if not ip:
                            continue
                        classification = rec.get("classification") or rec.get("trust_level") or ""
                        tags = rec.get("tags") or []
                        metadata = rec.get("metadata") or {}
                        cur.execute(
                            """
                            INSERT INTO greynoise_ips
                                (conflict, direction, ip, classification, tags_json, metadata_json, snapshot_timestamp, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                conflict,
                                direction,
                                ip,
                                classification,
                                Jsonb(tags if isinstance(tags, list) else []),
                                Jsonb(metadata if isinstance(metadata, dict) else {}),
                                snapshot_timestamp,
                                now,
                            ),
                        )
                conn.commit()
            return
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres _save_gnql_ips failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        for rec in ip_records[:50]:
            ip = rec.get("ip") or rec.get("address")
            if not ip:
                continue
            classification = rec.get("classification") or rec.get("trust_level") or ""
            tags = rec.get("tags") or []
            metadata = rec.get("metadata") or {}
            conn.execute(
                """INSERT INTO greynoise_ips (conflict, direction, ip, classification, tags_json, metadata_json, snapshot_timestamp, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conflict,
                    direction,
                    ip,
                    classification,
                    json.dumps(tags) if isinstance(tags, list) else json.dumps([]),
                    json.dumps(metadata) if isinstance(metadata, dict) else "{}",
                    snapshot_timestamp,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_latest_ips(conflict: str, limit: int = 30) -> List[Dict[str, Any]]:
    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT snapshot_timestamp FROM greynoise_ips
                        WHERE LOWER(conflict) = LOWER(%s) ORDER BY snapshot_timestamp DESC LIMIT 1
                        """,
                        (conflict,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return []
                    ts = row[0]
                    cur.execute(
                        """
                        SELECT ip, direction, classification, tags_json, metadata_json FROM greynoise_ips
                        WHERE LOWER(conflict) = LOWER(%s) AND snapshot_timestamp = %s ORDER BY id LIMIT %s
                        """,
                        (conflict, ts, limit),
                    )
                    rows = cur.fetchall()
            result = []
            for r in rows:
                ip, direction, classification, tags_json, metadata_json = r
                rec = {"ip": ip, "direction": direction, "classification": classification or ""}
                try:
                    tj = _json_data(tags_json) if tags_json is not None else []
                    mj = _json_data(metadata_json) if metadata_json is not None else {}
                    if tj:
                        rec["tags"] = tj
                    if mj:
                        rec["metadata"] = mj
                except (json.JSONDecodeError, TypeError):
                    pass
                result.append(rec)
            return result
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres get_latest_ips failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        row = conn.execute(
            "SELECT snapshot_timestamp FROM greynoise_ips WHERE LOWER(conflict) = LOWER(?) ORDER BY snapshot_timestamp DESC LIMIT 1",
            (conflict,),
        ).fetchone()
        if not row:
            return []
        ts = row[0]
        rows = conn.execute(
            """SELECT ip, direction, classification, tags_json, metadata_json FROM greynoise_ips
               WHERE LOWER(conflict) = LOWER(?) AND snapshot_timestamp = ? ORDER BY id LIMIT ?""",
            (conflict, ts, limit),
        ).fetchall()
        result = []
        for r in rows:
            ip, direction, classification, tags_json, metadata_json = r
            rec = {"ip": ip, "direction": direction, "classification": classification or ""}
            try:
                if tags_json:
                    rec["tags"] = json.loads(tags_json)
                if metadata_json:
                    rec["metadata"] = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(rec)
        return result
    finally:
        conn.close()


def _save_pending_tags(tags: List[str], conflict: str) -> None:
    if not tags:
        return
    now = _utc_now_iso()
    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    for tag in tags:
                        cur.execute(
                            """
                            SELECT 1 FROM greynoise_pending_tags WHERE tag_name = %s AND LOWER(conflict) = LOWER(%s)
                            """,
                            (tag, conflict),
                        )
                        if cur.fetchone():
                            continue
                        cur.execute(
                            """
                            INSERT INTO greynoise_pending_tags (tag_name, conflict, discovered_at, status)
                            VALUES (%s, %s, %s, 'pending')
                            """,
                            (tag, conflict, now),
                        )
                conn.commit()
            return
        except Exception as e:
            logger.warning("GreyNoise DB: Postgres _save_pending_tags failed, falling back to SQLite: %s", e)
    conn = _ensure_sqlite()
    try:
        for tag in tags:
            exists = conn.execute(
                "SELECT 1 FROM greynoise_pending_tags WHERE tag_name = ? AND LOWER(conflict) = LOWER(?)",
                (tag, conflict),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO greynoise_pending_tags (tag_name, conflict, discovered_at, status) VALUES (?, ?, ?, 'pending')",
                    (tag, conflict, now),
                )
        conn.commit()
    finally:
        conn.close()
